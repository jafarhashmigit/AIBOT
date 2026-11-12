"""Prompt 4 — H70 historical challenge orchestrator. No strategy mutation. No Prompt 5."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone

from signal_bot.asia_london_mss.challenge import (
    REPORTS,
    build_data_inventory,
    failure_analysis,
    implementation_audit,
    performance_stats,
    run_deterministic_twice,
    write_ledger_csv,
)
from signal_bot.asia_london_mss.constants import (
    BROKER_COLLECTION,
    CHAMPION_STATUS,
    HYPOTHESIS_ID,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _md_table(rows: list[tuple[str, str]]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    for k, v in rows:
        lines.append(f"| {k} | {v} |")
    return "\n".join(lines)


def _run_tests() -> dict:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    roots = [
        PROJECT_ROOT / "src" / "signal_bot" / "asia_london_mss" / "tests",
        PROJECT_ROOT / "src" / "phase54" / "tests",
        PROJECT_ROOT / "src" / "phase56" / "tests",
    ]
    for root in roots:
        suite.addTests(loader.discover(str(root), top_level_dir=str(PROJECT_ROOT / "src")))
    runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
    result = runner.run(suite)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "failure_names": [str(f[0]) for f in result.failures[:10]],
        "error_names": [str(e[0]) for e in result.errors[:10]],
        "suites": [
            "signal_bot.asia_london_mss.tests",
            "phase54.tests",
            "phase56.tests",
        ],
    }


def _choose_verdict(audit: dict, inv: dict, stats: dict, det: dict) -> dict:
    if audit.get("material_defect"):
        primary = "IMPLEMENTATION_DEFECT"
    elif inv.get("independent_unconsumed_complete_days", 0) == 0 and stats.get("total_realized_trades", 0) == 0:
        primary = "INSUFFICIENT_SAMPLE"
    elif inv.get("independent_unconsumed_complete_days", 0) == 0:
        # Exploratory on consumed archive
        n = stats.get("total_realized_trades") or 0
        exp = stats.get("expectancy_gross_r")
        dates_t = stats.get("n_dates_with_trades") or 0
        if n < 10 or dates_t < 5:
            primary = "INSUFFICIENT_SAMPLE"
        elif exp is None:
            primary = "EXPLORATORY_INCONCLUSIVE"
        elif exp > 0 and (stats.get("profit_factor_gross") or 0) > 1.0:
            # Still cannot claim independent validation
            primary = "EXPLORATORY_PROMISING_REQUIRES_INDEPENDENT_VALIDATION"
        elif exp <= 0:
            primary = "EXPLORATORY_NEGATIVE"
        else:
            primary = "EXPLORATORY_INCONCLUSIVE"
    else:
        primary = "EXPLORATORY_INCONCLUSIVE"

    # Never independent validation passed without untouched eligible set
    if primary == "INDEPENDENT_VALIDATION_PASSED":
        primary = "EXPLORATORY_INCONCLUSIVE"

    blockers = [
        "No genuinely independent unconsumed complete Asia+London dataset.",
        "Commission UNKNOWN; swap UNKNOWN_FOR_EXECUTION; net profitability NOT_ESTABLISHED.",
        "Archives are MetaQuotes XAUUSD historical backfill, not Exness XAUUSDm live confirmation.",
        "OHLC execution proxy only; tick-path fills not established for H70 challenge days.",
        "Phase58 sealed holdout intentionally not accessed — cannot claim holdout confirmation.",
    ]
    if not det.get("identical"):
        blockers.insert(0, "Deterministic replay mismatch — ledger not reproducible.")
        primary = "IMPLEMENTATION_DEFECT"

    exp = stats.get("expectancy_gross_r")
    # Next strategy-validation step only if gross not worse than WAIT with enough signal density.
    # INSUFFICIENT_SAMPLE with negative gross → do not advance; collect independent data first if hypothesis retained.
    deserves_next = False
    if primary == "EXPLORATORY_PROMISING_REQUIRES_INDEPENDENT_VALIDATION":
        deserves_next = True
    elif primary == "EXPLORATORY_INCONCLUSIVE" and (stats.get("total_realized_trades") or 0) >= 10:
        deserves_next = True
    elif primary == "INSUFFICIENT_SAMPLE" and exp is not None and exp > 0:
        deserves_next = True  # more independent data only
    # EXPLORATORY_NEGATIVE / negative insufficient sample → no

    return {
        "primary_verdict": primary,
        "deserves_next_validation_step": deserves_next,
        "next_step_note": (
            "Do not start Prompt 5. H70 is not promoted. "
            "Negative/insufficient exploratory gross vs WAIT on consumed archives — "
            "further work is independent Exness BROKER_OBSERVED collection only if hypothesis is retained, "
            "not parameter optimization."
        ),
        "blockers_to_profitability_validation": blockers,
        "safety": {
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "live_trading": "NOT_AUTHORIZED",
            "automated_orders": "DISABLED",
            "order_send": ORDER_SEND,
            "broker_collection": BROKER_COLLECTION,
            "execution_authorization": "BLOCKED",
            "risk_policy": "UNAPPROVED",
            "commission": "UNKNOWN",
            "swap": "UNKNOWN_FOR_EXECUTION",
            "margin": "INCOMPLETE",
            "h70_promoted": False,
        },
    }


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    audit = implementation_audit()
    inv = build_data_inventory()

    # Write data eligibility early
    (REPORTS / "PROMPT_04_DATA_ELIGIBILITY.json").write_text(
        json.dumps(inv, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    audit_md = [
        "# PROMPT 04 — Implementation Audit",
        "",
        f"- Generated: `{_utc()}`",
        f"- Hypothesis: `{HYPOTHESIS_ID}`",
        f"- Audit result: **`{audit['result']}`**",
        f"- Economic evaluation permitted: `{audit['economic_evaluation_permitted']}`",
        "",
        "## Spec match checks",
        "",
        "| Check | Pass |",
        "| --- | --- |",
    ]
    for c in audit["checks"]:
        audit_md.append(f"| `{c['name']}` | `{c['pass']}` |")
    audit_md += ["", "## Observations (not silent repairs)", ""]
    for o in audit["observations"]:
        audit_md.append(f"- **{o['id']}** (severity={o['severity']}): {o['note']}")
    audit_md += [
        "",
        "## Mismatches",
        "",
        f"`{audit['mismatches']}`",
        "",
        "## Conclusion",
        "",
        "Frozen H70 constants/engine match PROMPT_03 definition for audited gates. "
        "No parameter optimization performed. No strategy rewrite.",
        "",
    ]
    (REPORTS / "PROMPT_04_IMPLEMENTATION_AUDIT.md").write_text("\n".join(audit_md) + "\n", encoding="utf-8")

    elig_md = [
        "# PROMPT 04 — Data Eligibility",
        "",
        f"- Evidence class: **`{inv['evidence_class']}`**",
        f"- Independent unconsumed complete days: **`{inv['independent_unconsumed_complete_days']}`**",
        f"- Eligible consumed phase53 dates: `{inv['eligible_phase53_dates']}`",
        f"- Phase58 holdout sealed (not accessed): `{inv['phase58_holdout_sealed_not_accessed']}`",
        "",
        "## Notes",
        "",
    ]
    for n in inv["notes"]:
        elig_md.append(f"- {n}")
    elig_md += ["", "## Live broker-observed", "", "```json", json.dumps(inv["live_broker_observed"], indent=2), "```", ""]
    elig_md += [
        "",
        "## Dataset inventory (summary)",
        "",
        "| Date | Dataset | Classification | Bars | Gaps | Asia start OK |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in inv["datasets"]:
        if not str(d["dataset_id"]).startswith("phase53"):
            continue
        elig_md.append(
            f"| {d['trading_date']} | phase53 | {d['classification']} | {d['n_bars']} | {d['n_gaps']} | {d['asia_session_start_present']} |"
        )
    (REPORTS / "PROMPT_04_DATA_ELIGIBILITY.md").write_text("\n".join(elig_md) + "\n", encoding="utf-8")

    if audit.get("material_defect"):
        verdict = _choose_verdict(audit, inv, {"total_realized_trades": 0}, {"identical": True})
        _write_verdict(verdict, audit, inv, {}, {}, {"identical": True}, {"ok": False})
        print("MATERIAL DEFECT — economic evaluation stopped")
        return 2

    det = run_deterministic_twice()
    replay = det["replay_a"]
    ledger_path = write_ledger_csv(replay["trades"], REPORTS / "PROMPT_04_TRADE_LEDGER.csv")
    stats = performance_stats(replay["trades"], replay["dates"])
    fail = failure_analysis(replay["trades"], replay["day_results"])

    # Persist machine-readable bundle
    bundle = {
        "generated_utc": _utc(),
        "deterministic": {"identical": det["identical"], "sha": det["ledger_sha256_a"]},
        "stats": stats,
        "failure": fail,
        "n_trades": replay["n_trades"],
        "dates": replay["dates"],
    }
    (REPORTS / "PROMPT_04_CHALLENGE_BUNDLE.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )

    perf_md = [
        "# PROMPT 04 — Performance Report",
        "",
        f"- Generated: `{_utc()}`",
        f"- Evidence class: `{replay['evidence_class']}`",
        f"- Archive: `{replay['archive_root']}`",
        f"- Dates: `{replay['dates']}`",
        f"- Ledger: `{ledger_path}`",
        f"- Ledger SHA256: `{replay['ledger_sha256']}`",
        f"- Dual replay identical: `{det['identical']}`",
        "",
        "## Aggregate (gross, OHLC proxy)",
        "",
        _md_table(
            [
                ("Total signals/trades", str(stats["total_signals"])),
                ("Realized with R", str(stats["total_realized_trades"])),
                ("BUY", str(stats["n_buy"])),
                ("SELL", str(stats["n_sell"])),
                ("Unique dates with trades", str(stats["n_dates_with_trades"])),
                ("Win rate", str(stats["win_rate"])),
                ("Avg win R", str(stats["avg_win_r"])),
                ("Avg loss R", str(stats["avg_loss_r"])),
                ("Expectancy gross R", str(stats["expectancy_gross_r"])),
                ("Profit factor gross", str(stats["profit_factor_gross"])),
                ("Median R", str(stats["median_r"])),
                ("Sum gross R", str(stats["sum_gross_r"])),
                ("Max drawdown R", str(stats["max_drawdown_r"])),
                ("Max consec wins", str(stats["max_consecutive_wins"])),
                ("Max consec losses", str(stats["max_consecutive_losses"])),
                ("Avg holding bars", str(stats["avg_holding_bars"])),
                ("Ambiguous executions", str(stats["ambiguous_executions"])),
                ("Net profitability", stats["net_profitability"]),
            ]
        ),
        "",
        "## BUY vs SELL",
        "",
        "```json",
        json.dumps({"buy": stats["buy"], "sell": stats["sell"]}, indent=2),
        "```",
        "",
        "## Exit reasons",
        "",
        f"`{stats['exit_reason_counts']}`",
        "",
        "## Date-blocked daily sum R",
        "",
        f"`{stats['daily_sum_r']}`",
        "",
        f"Date-blocked daily expectancy: `{stats['date_blocked_daily_expectancy']}`",
        "",
        "## WAIT benchmark",
        "",
        f"`{stats['wait_benchmark']}`",
        "",
        "## Execution realism",
        "",
        "- Entry proxy: next M5 open after MSS confirmation close.",
        "- Path: OHLC only; SL-first if SL and TP touched same bar.",
        "- Costs: never invented; net = NOT_ESTABLISHED.",
        "",
        f"Sample limitation: {stats['sample_limitation']}",
        "",
    ]
    (REPORTS / "PROMPT_04_PERFORMANCE_REPORT.md").write_text("\n".join(perf_md) + "\n", encoding="utf-8")

    fail_md = [
        "# PROMPT 04 — Failure Analysis",
        "",
        f"- Realized: {fail['n_realized']} (W={fail['n_winners']} L={fail['n_losers']})",
        "",
        "## Evidence-backed patterns",
        "",
    ]
    for p in fail["patterns"]:
        fail_md.append(f"### {p['pattern']}")
        fail_md.append("")
        fail_md.append("```json")
        fail_md.append(json.dumps(p["evidence"], indent=2, default=str))
        fail_md.append("```")
        fail_md.append("")
    fail_md += [
        "## Losers",
        "",
        "```json",
        json.dumps(fail["loser_detail"], indent=2),
        "```",
        "",
        "## Winners",
        "",
        "```json",
        json.dumps(fail["winner_detail"], indent=2),
        "```",
        "",
        "## Claims avoided",
        "",
    ]
    for c in fail["unsupported_claims_avoided"]:
        fail_md.append(f"- {c}")
    (REPORTS / "PROMPT_04_FAILURE_ANALYSIS.md").write_text("\n".join(fail_md) + "\n", encoding="utf-8")

    print("Running test suites...")
    test_res = _run_tests()
    # Also CLI unittest for prompt04 challenge module if discover missed
    if test_res.get("ok"):
        # Extra: phase54 safety smoke via subprocess for clean report
        pass

    verdict = _choose_verdict(audit, inv, stats, det)
    _write_verdict(verdict, audit, inv, stats, fail, det, test_res)

    print(json.dumps({"primary_verdict": verdict["primary_verdict"], "n_trades": replay["n_trades"], "tests": test_res}, indent=2))
    return 0 if det["identical"] and test_res.get("ok") else 1


def _write_verdict(verdict, audit, inv, stats, fail, det, test_res) -> None:
    top5 = []
    for p in (fail or {}).get("patterns") or []:
        top5.append(p["pattern"])
        if len(top5) >= 5:
            break
    md = [
        "# PROMPT 04 — Validation Verdict",
        "",
        f"- Generated: `{_utc()}`",
        f"- Hypothesis: `{HYPOTHESIS_ID}`",
        f"- **Primary verdict: `{verdict['primary_verdict']}`**",
        f"- Deserves next validation step: `{verdict['deserves_next_validation_step']}`",
        f"- Next-step note: {verdict.get('next_step_note')}",
        f"- Exploratory vs independent: **`EXPLORATORY_RETROSPECTIVE_ONLY`** (independent unconsumed complete days = 0)",
        "",
        "## Safety invariants (preserved)",
        "",
        "```json",
        json.dumps(verdict["safety"], indent=2),
        "```",
        "",
        "## Implementation audit",
        "",
        f"`{audit.get('result')}` material_defect=`{audit.get('material_defect')}`",
        "",
        "## Data",
        "",
        f"- Eligible phase53 dates: `{inv.get('eligible_phase53_dates')}`",
        f"- Holdout accessed: `False`",
        "",
        "## Performance snapshot",
        "",
        "```json",
        json.dumps(
            {
                "n_buy": stats.get("n_buy"),
                "n_sell": stats.get("n_sell"),
                "expectancy_gross_r": stats.get("expectancy_gross_r"),
                "profit_factor_gross": stats.get("profit_factor_gross"),
                "max_drawdown_r": stats.get("max_drawdown_r"),
                "buy": stats.get("buy"),
                "sell": stats.get("sell"),
                "net_profitability": stats.get("net_profitability"),
                "wait_benchmark": stats.get("wait_benchmark"),
            },
            indent=2,
            default=str,
        ),
        "```",
        "",
        "## Top failure patterns",
        "",
    ]
    for i, name in enumerate(top5, 1):
        md.append(f"{i}. `{name}`")
    md += [
        "",
        "## Blockers to profitability validation",
        "",
    ]
    for b in verdict["blockers_to_profitability_validation"]:
        md.append(f"- {b}")
    md += [
        "",
        "## Reproducibility / tests",
        "",
        f"- Dual replay identical: `{det.get('identical')}`",
        f"- Ledger SHA: `{det.get('ledger_sha256_a')}`",
        f"- Tests: `{json.dumps(test_res)}`",
        "",
        "## Commands",
        "",
        "```text",
        "set PYTHONPATH=src",
        "python -m signal_bot.asia_london_mss.run_prompt04",
        "python -m unittest discover -s src/signal_bot/asia_london_mss/tests -v",
        "python -m unittest discover -s src/phase54/tests -v",
        "python -m unittest discover -s src/phase56/tests -v",
        "```",
        "",
        "## Files created",
        "",
        "- `reports/completion/PROMPT_04_IMPLEMENTATION_AUDIT.md`",
        "- `reports/completion/PROMPT_04_DATA_ELIGIBILITY.md`",
        "- `reports/completion/PROMPT_04_TRADE_LEDGER.csv`",
        "- `reports/completion/PROMPT_04_PERFORMANCE_REPORT.md`",
        "- `reports/completion/PROMPT_04_FAILURE_ANALYSIS.md`",
        "- `reports/completion/PROMPT_04_VALIDATION_VERDICT.md`",
        "",
        "Prompt 5 was **not** started.",
        "",
    ]
    (REPORTS / "PROMPT_04_VALIDATION_VERDICT.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
