"""Phase 42 runner — autonomous hypothesis discovery (no retired-candidate revival)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase42.constants import (
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
    RETIRED_CANDIDATES,
    TELEGRAM_MESSAGES_SENT,
    VALIDATION_DATES,
    file_sha256,
)
from phase42.constants import PHASE40_RAW_M5, SYMBOL
from phase42.evaluate import evaluate_all
from phase42.features import feature_dictionary
from phase42.hypotheses import frozen_hypothesis_registry
from phase42.independent import verify_independent
from phase42.learning import write_experience_stores
from phase42.progress import write_json
from phase42.qualification import decide_verdict
from phase42.ranking import rank_candidates

UTC = timezone.utc


def _input_manifest() -> dict[str, Any]:
    files = []
    for day in DISCOVERY_DATES + VALIDATION_DATES:
        p = PHASE40_RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl"
        if p.is_file():
            files.append({"path": str(p), "sha256": file_sha256(p), "bytes": p.stat().st_size})
    return {
        "n_m5_files_hashed": len(files),
        "files": files,
        "note": "Phase40 M5 sample hashes; full tick/H1 integrity assumed from Phase40 independent OK",
    }


def _report(
    *,
    registry: dict[str, Any],
    eval_payload: dict[str, Any],
    ranked: list[dict[str, Any]],
    indep: dict[str, Any],
    verdict: dict[str, Any],
    runtime: dict[str, Any],
) -> str:
    lines = [
        "# Phase 42 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Final verdict:** `{verdict.get('final_verdict')}`",
        f"**Best candidate:** `{verdict.get('best_candidate')}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        f"**Retired (not revived):** `{list(RETIRED_CANDIDATES)}`",
        "",
        "## Hypotheses generated",
        f"- Count: `{registry.get('n_hypotheses')}`",
        f"- Unique families: `{registry.get('n_families')}`",
        f"- Frozen before evaluation: `{registry.get('frozen_before_evaluation')}`",
        "",
        "## Rejected hypotheses",
        f"- Count: `{len(eval_payload.get('rejected') or [])}`",
    ]
    for r in eval_payload.get("rejected") or []:
        lines.append(f"- `{r['hypothesis_id']}` ({r['family']}): {r['reasons']}")

    lines += ["", "## Predictive results (validation split)"]
    for r in eval_payload.get("results") or []:
        v = r.get("validation") or {}
        lines.append(
            f"- `{r['hypothesis_id']}` status=`{r['status']}` n=`{v.get('n_events')}` "
            f"effect=`{v.get('effect')}` dates=`{v.get('n_dates')}` "
            f"bonferroni0=`{(v.get('bootstrap') or {}).get('bonferroni_excludes_zero')}`"
        )

    lines += ["", "## Decision-value results (HISTORICAL_HYPOTHETICAL only)"]
    for r in eval_payload.get("results") or []:
        d = r.get("decision_validation") or {}
        if d.get("skipped"):
            lines.append(f"- `{r['hypothesis_id']}`: skipped (`{d.get('reason')}`)")
        else:
            lines.append(
                f"- `{r['hypothesis_id']}`: scored=`{d.get('n_scored')}` mean_R=`{d.get('mean_net_r')}` "
                f"win=`{d.get('win_rate')}` decision_value=`{r.get('decision_value')}`"
            )

    lines += [
        "",
        "## Statistical corrections",
        "- Bonferroni across 10 frozen hypotheses (α=0.05/10).",
        "- Date-block bootstrap for conditional vs unconditional (or vs 0 for signed).",
        "- Leave-one-date-out on validation dates.",
        f"- Discovery dates: `{DISCOVERY_DATES}`",
        f"- Validation dates: `{VALIDATION_DATES}`",
        f"- Caveat: `{eval_payload.get('caveat')}`",
        "",
        "## Ranking",
    ]
    for row in ranked:
        lines.append(
            f"- #{row['rank']} `{row['hypothesis_id']}` score=`{row['rank_score']}` "
            f"status=`{row['status']}` effect=`{row.get('validation_effect')}`"
        )

    lines += [
        "",
        "## Independent verification",
        f"- OK: `{indep.get('ok')}` matched=`{indep.get('n_matched')}/{indep.get('n_hypotheses')}`",
        f"- Method: `{indep.get('method')}`",
        "",
        "## Execution feasibility",
        "- Bid/ask tick paths used for decision layer when predictive gates pass.",
        "- MetaQuotes-Demo spreads ≠ live broker costs; stress scenarios marked hypothetical.",
        "",
        "## Limitations",
        "- Only 10 previously examined Phase40 dates; cannot claim independent replication.",
        "- Sparse events for some families → many rejections for sample insufficiency.",
        "- Tick imbalance features reflect demo microstructure.",
        "- AGENT_SHADOW store empty (no live shadow run).",
        "- Overlapping events within days induce dependence (block bootstrap mitigates, does not eliminate).",
        "",
        "## Final decision",
        f"- Verdict: `{verdict.get('final_verdict')}`",
        f"- Reason: {verdict.get('reason')}",
        f"- Best candidate: `{verdict.get('best_candidate')}`",
        f"- Merits larger independent validation design: `{verdict.get('merits_independent_validation')}`",
        "",
        "## Safety",
        "- No Phase0–41 modifications; no commits/pushes; no broker orders; no packages; no holdout.",
        f"- Champion `{CHAMPION_STATUS}` | Production `{PRODUCTION_FINAL_ACTION}`",
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
    (docs / "PHASE_42_DISCOVERY_PROTOCOL.md").write_text(
        "\n".join(
            [
                "# Phase 42 — Discovery Protocol",
                "",
                "1. Freeze one primary hypothesis per family A–J before any scoring.",
                "2. Build causal features only; missing stays missing; completed H1 only.",
                "3. Chronological discovery (first 5 Phase40 dates) vs validation (last 5).",
                "4. Predictive tests before any trading decision evaluation.",
                "5. Bonferroni correction across 10 hypotheses; date-block bootstrap.",
                "6. Decision layer uses bid/ask ticks; HISTORICAL_HYPOTHETICAL ≠ AGENT_SHADOW.",
                "7. Do not revive H13_C or mean_reversion.",
                "8. Previously examined dates cannot unlock INDEPENDENT_VALIDATION_READY alone.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "PHASE_42_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 42 — Results",
                "",
                f"**Verdict:** `{verdict.get('final_verdict')}`",
                f"**Best:** `{verdict.get('best_candidate')}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                "See `reports/phase42/PHASE42_FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)

    registry = frozen_hypothesis_registry()
    write_json("frozen_hypothesis_registry.json", registry)
    write_json("feature_dictionary.json", feature_dictionary())
    write_json("discovery_validation_manifest.json", {
        "discovery_dates": DISCOVERY_DATES,
        "validation_dates": VALIDATION_DATES,
        "purge_bars": 12,
        "retired_not_revived": list(RETIRED_CANDIDATES),
        "input_hashes": _input_manifest(),
    })

    eval_payload = evaluate_all()
    write_json("evaluation_results.json", eval_payload)
    write_json("rejected_hypothesis_registry.json", {"rejected": eval_payload.get("rejected")})

    ranked = rank_candidates(eval_payload)
    write_json("candidate_ranking.json", ranked)

    write_experience_stores(eval_payload)

    indep = verify_independent(eval_payload)
    write_json("independent_verification.json", indep)

    verdict = decide_verdict(eval_payload, ranked, indep_ok=bool(indep.get("ok")))
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
        "phase": 42,
        "recipe_id": RECIPE_ID,
        "final_verdict": verdict.get("final_verdict"),
        "best_candidate": verdict.get("best_candidate"),
        "verdict_reason": verdict.get("reason"),
        "n_hypotheses": registry.get("n_hypotheses"),
        "n_families": registry.get("n_families"),
        "n_rejected": len(eval_payload.get("rejected") or []),
        "independent_ok": indep.get("ok"),
        "retired_not_revived": list(RETIRED_CANDIDATES),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "merits_independent_validation": verdict.get("merits_independent_validation"),
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    (REPORTS_DIR / "PHASE42_FINAL_REPORT.md").write_text(
        _report(
            registry=registry,
            eval_payload=eval_payload,
            ranked=ranked,
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
