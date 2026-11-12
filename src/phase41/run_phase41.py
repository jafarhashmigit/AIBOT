"""Phase 41 runner — full-session frozen strategy retest (no MT5 live, no tuning)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase41.audit import verify_and_freeze_specs
from phase41.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    H13_C_STATUS,
    HOLDOUT_ACCESSES,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
)
from phase41.data import build_eligibility_table
from phase41.evaluate import evaluate_both
from phase41.independent_eval import compare_independent
from phase41.progress import write_json
from phase41.qualification import verdict_for_candidate

UTC = timezone.utc


def _fmt(x: Any) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if x != x:  # NaN
            return "n/a"
        return f"{x:.4f}"
    return str(x)


def _report(
    *,
    spec: dict[str, Any],
    eligibility: dict[str, Any],
    results: dict[str, Any],
    indep: dict[str, Any],
    verdicts: dict[str, Any],
    best: str,
    runtime: dict[str, Any],
) -> str:
    lines: list[str] = [
        "# Phase 41 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Best candidate:** `{best}`",
        f"**H13_C verdict:** `{verdicts['H13_C'].get('verdict')}`",
        f"**Mean Reversion verdict:** `{verdicts['mean_reversion'].get('verdict')}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
        "",
        "## 1. Frozen input manifest and hashes",
        f"- Spec OK: `{spec.get('spec_ok')}`",
        f"- Discrepancies: `{spec.get('discrepancies')}`",
        f"- Phase40 integrity OK: `{spec.get('phase40_integrity', {}).get('ok')}`",
        f"- Phase40 files hashed: `{spec.get('phase40_integrity', {}).get('n_files')}`",
        "Artifact: `frozen_evaluation_manifest.json`",
        "",
        "## 2. Data eligibility",
        f"- Dates: `{eligibility.get('n_dates')}`",
        f"- H13_C eligible slots (data only): `{eligibility.get('H13_C_total_eligible_slots')}`",
        f"- MR eligible slots (data only): `{eligibility.get('mean_reversion_total_eligible_slots')}`",
        f"- Caveat: `{eligibility.get('caveat')}`",
        "",
        "## 3. Exact candidate specifications",
        f"- H13_C cuts: `{spec['candidates']['H13_C']['cuts']}`",
        f"- H13_C rules: `{spec['candidates']['H13_C']['rules']}`",
        f"- MR params: `{spec['candidates']['mean_reversion']['parameters']}`",
        f"- H13_C frozen status: `{H13_C_STATUS}`",
        "",
    ]

    for cid in ("H13_C", "mean_reversion"):
        r = results[cid]
        s = r["summary"]
        lines += [
            f"## Candidate `{cid}`",
            "",
            "### 4–5. Signals / scored / unscored",
            f"- Signals (BUY/SELL): `{s.get('n_signals')}`",
            f"- Scored: `{s.get('n_scored')}`",
            f"- Insufficient coverage: `{s.get('n_insufficient_coverage')}`",
            f"- Uncertain executions: `{s.get('n_uncertain')}`",
            f"- BUY / SELL scored: `{s.get('n_buy')}` / `{s.get('n_sell')}`",
            "",
            "### 6. Full performance metrics",
            f"- Mean net R: `{_fmt(s.get('mean_r'))}`",
            f"- Median net R: `{_fmt(s.get('median_r'))}`",
            f"- Win rate: `{_fmt(s.get('win_rate'))}`",
            f"- Profit factor: `{_fmt(s.get('profit_factor'))}`",
            f"- Max DD (R): `{_fmt(s.get('max_dd_r'))}`",
            f"- Max consecutive losses: `{s.get('max_consec_losses')}`",
            f"- Mean MAE_R / MFE_R: `{_fmt(s.get('mean_mae_r'))}` / `{_fmt(s.get('mean_mfe_r'))}`",
            f"- BUY mean R / SELL mean R: `{_fmt(s.get('buy_mean_r'))}` / `{_fmt(s.get('sell_mean_r'))}`",
            f"- Mean entry spread: `{_fmt(s.get('mean_entry_spread'))}`",
            f"- Exit reasons: `{s.get('exit_reason_counts')}`",
            "",
            "### 7. All 10 date-level results",
        ]
        for day, row in (r.get("by_date") or {}).items():
            lines.append(
                f"- `{day}`: n=`{row.get('n')}` mean_r=`{_fmt(row.get('mean_r'))}` "
                f"sum_r=`{_fmt(row.get('sum_r'))}` signals=`{row.get('n_signals')}`"
            )
        lines += [
            "",
            "### 8. BUY/SELL and session",
            f"- By session: `{r.get('by_session')}`",
            "",
            "### 9. Execution cost sensitivity (hypothetical; not live broker)",
        ]
        # show key scenarios
        for sc in (r.get("scenarios") or [])[:12]:
            lines.append(
                f"- slip=`{sc['slippage_per_side']}` comm=`{sc['commission_per_side']}` "
                f"widen=`{sc['spread_widen_mult']}`: mean_r=`{_fmt(sc['mean_scenario_net_r'])}` "
                f"pct_pos=`{_fmt(sc['pct_trades_positive'])}`"
            )
        be = r.get("break_even") or {}
        lines += [
            f"- Break-even extra USD/trade: `{_fmt(be.get('max_extra_usd_per_trade_before_zero_expectancy'))}`",
            "",
            "### 10. Drawdown and risk",
            f"- max_dd_r=`{_fmt(s.get('max_dd_r'))}` max_consec_losses=`{s.get('max_consec_losses')}`",
            "",
            "### 11. Statistical validation",
            f"- Independent dates with scores: `{r.get('n_independent_dates_with_scores')}`",
            f"- Bootstrap: `{r.get('bootstrap')}`",
            f"- Leave-one-date-out: `{r.get('leave_one_date_out')}`",
            "",
            f"### Verdict: `{verdicts[cid].get('verdict')}`",
            f"- Reason: {verdicts[cid].get('reason')}",
            f"- Merits larger independent validation: `{verdicts[cid].get('merits_larger_independent_validation')}`",
            "",
        ]

    lines += [
        "## 12. Independent recomputation",
        f"- OK: `{indep.get('ok')}`",
        f"- Method: `{indep.get('method')}`",
        f"- By candidate: `{ {k: {x: v.get(x) for x in ('n_primary','n_independent','exact_matches','n_mismatches','ok')} for k,v in (indep.get('by_candidate') or {}).items()} }`",
        "",
        "## 13. Known limitations",
        "- These 10 dates were previously examined (Phase38/39/40) — exploratory retest, not independent OOS.",
        "- MetaQuotes-Demo bid/ask ≠ live broker execution truth.",
        "- Ambiguous same-tick TP/SL treated adversely in primary metrics.",
        "- No unverified commission/slippage in primary view; stress scenarios are hypothetical.",
        "- Overlapping signals not portfolio-netted.",
        "",
        "## 14. Candidate verdicts",
        f"- H13_C: `{verdicts['H13_C']}`",
        f"- mean_reversion: `{verdicts['mean_reversion']}`",
        "",
        "## 15. Best next experiment",
    ]
    h13_m = bool(verdicts["H13_C"].get("merits_larger_independent_validation"))
    mr_m = bool(verdicts["mean_reversion"].get("merits_larger_independent_validation"))
    if h13_m or mr_m:
        lines.append(
            "- Design a **new independent date set** (not these 10), pre-register freeze, "
            "bound wall-clock acquisition, then retest only candidates marked merits_larger_independent_validation=True."
        )
    else:
        lines.append(
            "- Retire both frozen candidates from active research priority; open new market hypotheses "
            "(fresh feature families / regimes) under a new frozen registry before any more capital on these specs."
        )

    lines += [
        "",
        "## Final summary",
        f"- Best candidate: `{best}`",
        f"- H13_C: `{verdicts['H13_C'].get('verdict')}`",
        f"- Mean Reversion: `{verdicts['mean_reversion'].get('verdict')}`",
        f"- Either merits larger independent validation: `{h13_m or mr_m}`",
        f"- Champion: `{CHAMPION_STATUS}`",
        f"- Production: `{PRODUCTION_FINAL_ACTION}`",
        "",
        "## Safety confirmation",
        "- No MT5 live/forward connection for trading.",
        "- No broker orders; no packages installed; no Discord/Telegram; no holdout access.",
        "- No parameter optimization; no model training; no new strategies.",
        "- No Phase0–40 artifacts modified; no commits or pushes.",
        f"- Counters: orders/Discord/Telegram/packages/holdout/commit/push/mt5 = "
        f"{BROKER_ORDERS}/{DISCORD_MESSAGES_SENT}/{TELEGRAM_MESSAGES_SENT}/"
        f"{PACKAGES_INSTALLED}/{HOLDOUT_ACCESSES}/{GIT_COMMIT}/{GIT_PUSH}/{MT5_CONNECTIONS}",
        f"- Runtime: `{runtime.get('DURATION')}`",
        "",
    ]
    return "\n".join(lines)


def _docs(final: dict[str, Any]) -> None:
    docs = PROJECT_ROOT / "docs" / "agent"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "PHASE_41_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 41 — Research Plan",
                "",
                "Full-session frozen retest of H13_C and mean_reversion on Phase40 MT5 archives.",
                "Execution-aware bid/ask; no parameter changes; adversarial verdicts.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    v = final.get("verdicts") or {}
    (docs / "PHASE_41_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 41 — Results",
                "",
                f"**Best:** `{final.get('best_candidate')}`",
                f"**H13_C:** `{v.get('H13_C', {}).get('verdict')}`",
                f"**mean_reversion:** `{v.get('mean_reversion', {}).get('verdict')}`",
                f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}`",
                "",
                "See `reports/phase41/PHASE41_FINAL_REPORT.md`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)

    spec = verify_and_freeze_specs()
    if not spec.get("spec_ok"):
        final = {
            "phase": 41,
            "recipe_id": RECIPE_ID,
            "blocked": True,
            "reason": "spec or Phase40 integrity discrepancy",
            "discrepancies": spec.get("discrepancies"),
            "best_candidate": "NONE",
            "verdicts": {
                "H13_C": {"verdict": "EXECUTION_MODEL_BLOCKED", "reason": "spec discrepancy"},
                "mean_reversion": {"verdict": "EXECUTION_MODEL_BLOCKED", "reason": "spec discrepancy"},
            },
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
        }
        write_json("final_verdict.json", final)
        (REPORTS_DIR / "PHASE41_FINAL_REPORT.md").write_text(
            "# Phase 41 — BLOCKED\n\n" + json.dumps(final, indent=2) + "\n",
            encoding="utf-8",
        )
        _docs(final)
        print(json.dumps(final, indent=2))
        return final

    eligibility = build_eligibility_table()
    write_json("eligibility_table.json", eligibility)

    results = evaluate_both()
    # Persist evaluations without dumping every tick path detail twice if huge
    for cid in ("H13_C", "mean_reversion"):
        slim = {k: v for k, v in results[cid].items() if k != "trades"}
        slim["trades"] = results[cid]["trades"]  # keep full audit trail as required
        write_json(f"evaluation_{cid}.json", slim)

    indep = compare_independent(results)
    write_json("independent_recomputation.json", indep)

    verdicts = {
        "H13_C": verdict_for_candidate(results["H13_C"], indep_ok=indep["by_candidate"]["H13_C"]["ok"]),
        "mean_reversion": verdict_for_candidate(
            results["mean_reversion"], indep_ok=indep["by_candidate"]["mean_reversion"]["ok"]
        ),
    }
    write_json("candidate_verdicts.json", verdicts)

    # Best candidate selection — adversarial
    best = "NONE"
    rank = {"PROMISING_BUT_UNCONFIRMED": 2, "INSUFFICIENT_EVIDENCE": 1, "EDGE_REJECTED": 0, "EXECUTION_MODEL_BLOCKED": -1}
    scored_cands = []
    for cid in ("H13_C", "mean_reversion"):
        v = verdicts[cid]["verdict"]
        mean_r = results[cid]["summary"].get("mean_r")
        if v == "PROMISING_BUT_UNCONFIRMED" and mean_r is not None and mean_r > 0:
            scored_cands.append((rank[v], mean_r, cid))
    if scored_cands:
        scored_cands.sort(reverse=True)
        best = scored_cands[0][2]

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
    }
    write_json("runtime.json", runtime)

    final = {
        "phase": 41,
        "recipe_id": RECIPE_ID,
        "best_candidate": best,
        "verdicts": verdicts,
        "summaries": {
            "H13_C": results["H13_C"]["summary"],
            "mean_reversion": results["mean_reversion"]["summary"],
        },
        "n_independent_dates": {
            "H13_C": results["H13_C"]["n_independent_dates_with_scores"],
            "mean_reversion": results["mean_reversion"]["n_independent_dates_with_scores"],
        },
        "eligibility_totals": {
            "H13_C": eligibility.get("H13_C_total_eligible_slots"),
            "mean_reversion": eligibility.get("mean_reversion_total_eligible_slots"),
        },
        "independent_ok": indep.get("ok"),
        "either_merits_larger_validation": bool(
            verdicts["H13_C"].get("merits_larger_independent_validation")
            or verdicts["mean_reversion"].get("merits_larger_independent_validation")
        ),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "h13_c_frozen_status": H13_C_STATUS,
        "no_parameter_changes": True,
        "no_model_training": True,
        "broker_orders": BROKER_ORDERS,
        "mt5_connections": MT5_CONNECTIONS,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    (REPORTS_DIR / "PHASE41_FINAL_REPORT.md").write_text(
        _report(
            spec=spec,
            eligibility=eligibility,
            results=results,
            indep=indep,
            verdicts=verdicts,
            best=best,
            runtime=runtime,
        )
        + "\n",
        encoding="utf-8",
    )
    _docs(final)
    print(
        json.dumps(
            {
                "best_candidate": best,
                "verdicts": {k: v.get("verdict") for k, v in verdicts.items()},
                "summaries": final["summaries"],
                "independent_ok": indep.get("ok"),
                "runtime": runtime,
            },
            indent=2,
        )
    )
    return final


if __name__ == "__main__":
    main()
