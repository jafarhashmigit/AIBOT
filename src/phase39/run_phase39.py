"""Phase 39 runner — disprove-first edge validation on Phase38 MT5 archive."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase39.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    H13_C_STATUS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
)
from phase39.data import build_eligibility_table
from phase39.evaluate import evaluate_both
from phase39.frozen_spec import verify_and_freeze
from phase39.independent import compare_independent
from phase39.progress import write_json
from phase39.qualification import verdict_for_candidate

UTC = timezone.utc


def _write_docs(final: dict[str, Any], runtime: dict[str, Any]) -> None:
    docs = PROJECT_ROOT / "docs" / "agent"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE_39_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 39 — Research Plan",
                "",
                "Execution-reality validation of frozen H13_C and mean_reversion on Phase38 MT5 data.",
                "Attempt to disprove both. No parameter tuning. No production change.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "PHASE_39_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 39 — Results",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                f"**Best candidate:** `{final.get('best_candidate')}`",
                f"**H13_C:** `{final.get('verdicts', {}).get('H13_C', {}).get('verdict')}`",
                f"**mean_reversion:** `{final.get('verdicts', {}).get('mean_reversion', {}).get('verdict')}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                f"- START_UTC: `{runtime['START_UTC']}`",
                f"- END_UTC: `{runtime['END_UTC']}`",
                f"- DURATION: `{runtime['DURATION']}`",
                "",
                "See `reports/phase39/PHASE39_FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _report_md(final: dict[str, Any], runtime: dict[str, Any]) -> str:
    v = final.get("verdicts") or {}
    return "\n".join(
        [
            "# Phase 39 — Final Report",
            "",
            f"**Best candidate:** `{final.get('best_candidate')}`",
            f"**Edge status:** `{final.get('edge_status')}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
            f"**H13_C status (frozen):** `{H13_C_STATUS}`",
            "",
            "## 1. Frozen candidate specification",
            "See `frozen_candidate_spec.json`. Spec verification "
            f"`{'OK' if final.get('spec_ok') else 'FAILED'}` — discrepancies: "
            f"`{final.get('spec_discrepancies')}`",
            "",
            "## 2. Data eligibility",
            "Phase38 only: 10 dates, M5 full-day, ticks **12:00–15:00 UTC**.",
            "See `eligibility_table.json`.",
            "",
            "## 3. Execution methodology",
            "BUY: entry ASK, exit BID. SELL: entry BID, exit ASK.",
            "TP/SL via chronological ticks; ambiguous same-tick barriers → adverse FAIL.",
            "Missing tick path → `INSUFFICIENT_TICK_COVERAGE`. No fabrication.",
            "",
            "## 4–8. Results",
            f"- H13_C: `{v.get('H13_C')}`",
            f"- mean_reversion: `{v.get('mean_reversion')}`",
            "Details: `evaluation_H13_C.json`, `evaluation_mean_reversion.json`.",
            "",
            "## 9. Statistical limitations",
            "Independent date count and scored trades are small; do not claim significance.",
            "",
            "## 10. Independent recomputation",
            f"`{final.get('independent_ok')}` — see `independent_comparison.json`.",
            "",
            "## 11. Phase35 reconciliation",
            "Phase35 used Dukascopy multi-day continuous corpus; Phase39 uses Demo MT5 "
            "isolated dates with 3h tick windows — not a direct like-for-like replication.",
            "",
            "## 12–13. Best / rejections",
            f"- Best: `{final.get('best_candidate')}`",
            f"- Edge status: `{final.get('edge_status')}`",
            f"- Larger study warranted: `{final.get('merits_larger_validation')}`",
            "",
            "## 14. Most valuable next experiment",
            final.get("next_experiment") or "n/a",
            "",
            f"## 15. Runtime: `{runtime.get('DURATION')}`",
            "",
            "## Safety",
            f"Orders/Discord/Telegram/packages/holdout/commit/push = "
            f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
            f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}",
            "",
        ]
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    spec = verify_and_freeze()
    if not spec.get("spec_ok"):
        # Stop and report rather than guess
        end = datetime.now(UTC)
        runtime = {
            "START_UTC": start_s,
            "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "DURATION_SECONDS": (end - start).total_seconds(),
            "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
        }
        final = {
            "phase": 39,
            "recipe_id": RECIPE_ID,
            "best_candidate": "NONE",
            "edge_status": "insufficient evidence",
            "spec_ok": False,
            "spec_discrepancies": spec.get("discrepancies"),
            "verdicts": {
                "H13_C": {"verdict": "EXECUTION_MODEL_BLOCKED", "reason": "spec discrepancy"},
                "mean_reversion": {"verdict": "EXECUTION_MODEL_BLOCKED", "reason": "spec discrepancy"},
            },
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "runtime": runtime,
        }
        write_json("final_verdict.json", final)
        (REPORTS_DIR / "PHASE39_FINAL_REPORT.md").write_text(_report_md(final, runtime) + "\n", encoding="utf-8")
        _write_docs(final, runtime)
        print(json.dumps(final, indent=2))
        return final

    eligibility = build_eligibility_table()
    write_json("eligibility_table.json", eligibility)

    results = evaluate_both()
    # strip heavy trade dumps to separate files
    for cid, res in results.items():
        slim = {k: v for k, v in res.items() if k != "trades"}
        write_json(f"evaluation_{cid}.json", slim)
        write_json(f"trades_{cid}.json", {"n": len(res["trades"]), "trades": res["trades"]})

    indep = compare_independent(results)
    write_json("independent_comparison.json", indep)

    verdicts = {
        "H13_C": verdict_for_candidate(results["H13_C"], indep_ok=indep["by_candidate"]["H13_C"]["ok"]),
        "mean_reversion": verdict_for_candidate(
            results["mean_reversion"], indep_ok=indep["by_candidate"]["mean_reversion"]["ok"]
        ),
    }
    write_json("verdicts.json", verdicts)

    # Best candidate selection — never promote
    best = "NONE"
    edge_status = "insufficient evidence"
    merits = False
    for cid in ("mean_reversion", "H13_C"):
        v = verdicts[cid]["verdict"]
        if v == "PROMISING_BUT_UNCONFIRMED":
            best = cid
            edge_status = "unconfirmed"
            merits = True
            break
        if v == "EDGE_REJECTED" and best == "NONE":
            edge_status = "rejected"
    if all(verdicts[c]["verdict"] == "INSUFFICIENT_EVIDENCE" for c in verdicts):
        edge_status = "insufficient evidence"
        best = "NONE"
    if any(verdicts[c]["verdict"] == "EXECUTION_MODEL_BLOCKED" for c in verdicts) and best == "NONE":
        edge_status = "rejected"

    next_exp = (
        "Acquire continuous multi-day MT5 M5+full-session ticks (not only 12:00–15:00) "
        "covering ≥10 independent dates with H1 history depth ≥20 hours for H13_C, "
        "then re-run execution-reality validation without parameter changes."
    )

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 39,
        "recipe_id": RECIPE_ID,
        "best_candidate": best,
        "edge_status": edge_status,
        "merits_larger_validation": merits,
        "next_experiment": next_exp,
        "spec_ok": True,
        "spec_discrepancies": [],
        "verdicts": verdicts,
        "summaries": {
            "H13_C": results["H13_C"]["summary"],
            "mean_reversion": results["mean_reversion"]["summary"],
        },
        "n_dates_eligibility": eligibility.get("n_dates"),
        "independent_ok": indep.get("ok"),
        "h13_c_frozen_status": H13_C_STATUS,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "broker_orders": BROKER_ORDERS,
        "discord_sent": DISCORD_MESSAGES_SENT > 0,
        "telegram_sent": TELEGRAM_MESSAGES_SENT > 0,
        "packages_installed": PACKAGES_INSTALLED,
        "holdout_accessed": HOLDOUT_ACCESSES > 0,
        "git_commit": GIT_COMMIT,
        "git_push": GIT_PUSH,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    (REPORTS_DIR / "PHASE39_FINAL_REPORT.md").write_text(_report_md(final, runtime) + "\n", encoding="utf-8")
    _write_docs(final, runtime)
    print(
        json.dumps(
            {
                "best_candidate": best,
                "edge_status": edge_status,
                "verdicts": verdicts,
                "summaries": final["summaries"],
                "independent_ok": indep.get("ok"),
                "runtime": runtime,
            },
            indent=2,
            default=str,
        )
    )
    return final


if __name__ == "__main__":
    main()
