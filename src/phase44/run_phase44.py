"""Phase 44 runner — preregistered independent edge discovery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase44.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    DISCOVERY_DATES,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    RETIRED,
    TELEGRAM_MESSAGES_SENT,
    VALIDATION_DATES,
)
from phase44.corpus import build_corpus
from phase44.evaluate import screen_discovery, validate_frozen
from phase44.hypotheses import freeze_registry
from phase44.independent import verify_independent
from phase44.learning import write_experience_stores
from phase44.preflight import run_preflight
from phase44.progress import write_json
from phase44.qualification import decide_verdict

UTC = timezone.utc


def _report(
    *,
    preflight: dict[str, Any],
    discovery: dict[str, Any],
    frozen: dict[str, Any],
    validation: dict[str, Any] | None,
    indep: dict[str, Any],
    verdict: dict[str, Any],
    runtime: dict[str, Any],
) -> str:
    lines = [
        "# Phase 44 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict.get('final_verdict')}`",
        f"**Best candidate:** `{verdict.get('best_candidate')}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        f"**Retired not revived:** `{list(RETIRED)}`",
        "",
        "## Preflight",
        f"- OK: `{preflight.get('ok')}` fails=`{preflight.get('n_fails')}`",
        f"- Phase43 indep OK: `{preflight.get('phase43_independent_ok')}`",
        f"- Unusual tick counts: `{preflight.get('unusual_tick_counts')}`",
        f"- Demo spread note: {preflight.get('demo_spread_note')}",
        "",
        "## Frozen allocation",
        f"- Discovery (15): `{DISCOVERY_DATES}`",
        f"- Validation (15): `{VALIDATION_DATES}`",
        "- Never reallocated by returns.",
        "",
        "## Hypotheses",
        f"- Primary count: `{frozen.get('n_hypotheses')}`",
        f"- Registry SHA-256: `{frozen.get('registry_sha256')}`",
        "",
        "## Discovery results",
    ]
    for r in discovery.get("results") or []:
        p = r.get("discovery_predictive") or {}
        lines.append(
            f"- `{r['hypothesis_id']}` status=`{r['status']}` n=`{p.get('n_events')}` "
            f"effect=`{p.get('effect')}` dates=`{p.get('n_dates')}` "
            f"bonf0=`{(p.get('bootstrap') or {}).get('bonferroni_excludes_zero')}` "
            f"reasons=`{r.get('rejection_reasons')}`"
        )
    lines += ["", "## Validation (one-shot)"]
    if not validation:
        lines.append("- Not run (no survivors or blocked).")
    else:
        for r in validation.get("results") or []:
            p = r.get("validation_predictive") or {}
            d = r.get("validation_decision") or {}
            lines.append(
                f"- `{r['hypothesis_id']}` pred_confirmed=`{r.get('predictive_confirmed')}` "
                f"dec_confirmed=`{r.get('decision_confirmed')}` n=`{p.get('n_events')}` "
                f"effect=`{p.get('effect')}` mean_R=`{d.get('mean_net_r')}` "
                f"PF=`{d.get('profit_factor')}` maxDD=`{d.get('max_dd_r')}` "
                f"reasons=`{r.get('rejection_reasons')}`"
            )
            lines.append(f"  - by_date: `{d.get('by_date')}`")

    lines += [
        "",
        "## Independent verification",
        f"- OK: `{indep.get('ok')}` matched=`{indep.get('n_matched')}/{indep.get('n_hypotheses')}`",
        "",
        "## Experience stores",
        "- HISTORICAL_HYPOTHETICAL populated from counterfactual fills.",
        "- AGENT_SHADOW empty (no live shadow).",
        "",
        "## Limitations",
        "- MetaQuotes-Demo ≠ live broker.",
        "- Max 5 hypotheses; overlapping events induce dependence.",
        "- Prior-day OHLC may fall back to Phase40 archive for level features only.",
        "- INDEPENDENT_VALIDATION_READY is not production authorization.",
        "",
        "## Final decision",
        f"- Verdict: `{verdict.get('final_verdict')}`",
        f"- Reason: {verdict.get('reason')}",
        f"- Best: `{verdict.get('best_candidate')}`",
        "",
        "## Safety",
        "- No Phase0–43 modifications; no commits/pushes; no broker orders; no packages; no holdout.",
        f"- Counters orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime: `{runtime.get('DURATION')}`",
        "",
    ]
    return "\n".join(lines)


def _docs(verdict: dict[str, Any]) -> None:
    docs = PROJECT_ROOT / "docs" / "agent"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE_44_PROTOCOL.md").write_text(
        "\n".join(
            [
                "# Phase 44 — Protocol",
                "",
                "1. Preflight Phase43 integrity.",
                "2. Lock discovery/validation dates from Phase43 allocation.",
                "3. Freeze ≤5 new hypotheses (no Phase42/H13/MR revival).",
                "4. Screen on discovery only.",
                "5. Hash frozen registry before opening validation outcomes.",
                "6. One-shot validation; no retuning.",
                "7. Bonferroni (n=5), date-block bootstrap, LODO.",
                "8. HISTORICAL_HYPOTHETICAL ≠ AGENT_SHADOW.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "PHASE_44_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 44 — Results",
                "",
                f"**Verdict:** `{verdict.get('final_verdict')}`",
                f"**Best:** `{verdict.get('best_candidate')}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                "See `reports/phase44/PHASE44_FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)

    preflight = run_preflight()
    if not preflight.get("ok"):
        verdict = decide_verdict({"results": [], "survivor_ids": [], "rejected": []}, None, indep_ok=True, preflight_ok=False)
        write_json("qualification.json", verdict)
        final = {
            "phase": 44,
            "final_verdict": verdict["final_verdict"],
            "best_candidate": "NONE",
            "preflight_ok": False,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
        }
        write_json("final_verdict.json", final)
        (REPORTS_DIR / "PHASE44_FINAL_REPORT.md").write_text(
            "# Phase 44 — BLOCKED\n\n" + json.dumps(preflight, indent=2) + "\n",
            encoding="utf-8",
        )
        _docs(verdict)
        print(json.dumps(final, indent=2))
        return final

    # Freeze hypotheses BEFORE discovery scoring artifacts are finalized (rules locked)
    frozen_pre = freeze_registry(stage="pre_discovery")
    write_json("allocation_lock.json", {
        "discovery_dates": DISCOVERY_DATES,
        "validation_dates": VALIDATION_DATES,
        "reallocation_forbidden": True,
    })

    # Discovery corpus only — do not build validation corpus yet
    disc_corpus = build_corpus(DISCOVERY_DATES, need_ticks=True)
    discovery = screen_discovery(disc_corpus, DISCOVERY_DATES)
    write_json("discovery_results.json", discovery)

    indep = verify_independent(discovery, DISCOVERY_DATES)
    write_json("independent_verification.json", indep)

    # Freeze survivors + full protocol hash BEFORE opening validation
    frozen = freeze_registry(stage="pre_validation")
    frozen["survivor_ids_for_validation"] = list(discovery.get("survivor_ids") or [])
    frozen["validation_protocol"] = {
        "dates": VALIDATION_DATES,
        "one_shot": True,
        "no_retuning": True,
        "tests": ["predictive_effect", "bonferroni", "lodo", "bidask_decision", "stress"],
    }
    write_json("frozen_hypothesis_registry_pre_validation.json", frozen)

    validation = None
    if discovery.get("survivor_ids"):
        # NOW open validation outcomes
        val_corpus = build_corpus(VALIDATION_DATES, need_ticks=True)
        validation = validate_frozen(val_corpus, VALIDATION_DATES, discovery["survivor_ids"])
        write_json("validation_results.json", validation)

    write_experience_stores(discovery, validation)
    verdict = decide_verdict(discovery, validation, indep_ok=bool(indep.get("ok")), preflight_ok=True)
    write_json("qualification.json", verdict)

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 44,
        "recipe_id": RECIPE_ID,
        "final_verdict": verdict.get("final_verdict"),
        "best_candidate": verdict.get("best_candidate"),
        "verdict_reason": verdict.get("reason"),
        "n_hypotheses": frozen_pre.get("n_hypotheses"),
        "survivor_ids": discovery.get("survivor_ids"),
        "independent_ok": indep.get("ok"),
        "preflight_ok": True,
        "retired_not_revived": list(RETIRED),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    (REPORTS_DIR / "PHASE44_FINAL_REPORT.md").write_text(
        _report(
            preflight=preflight,
            discovery=discovery,
            frozen=frozen,
            validation=validation,
            indep=indep,
            verdict=verdict,
            runtime=runtime,
        )
        + "\n",
        encoding="utf-8",
    )
    _docs(verdict)
    print(json.dumps(final, indent=2))
    return final


if __name__ == "__main__":
    main()
