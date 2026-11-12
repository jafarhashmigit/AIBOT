"""Phase 68 runner."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase68.adversarial import run_adversarial_tests
from phase68.competing import competing_outcomes_report
from phase68.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    CHAMPION_STATUS,
    DOCS_DIR,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
)
from phase68.displacement import build_displacement_report, extract_events
from phase68.execution import execution_realism
from phase68.integrity import audit_integrity
from phase68.live_integrity import audit_live_evidence
from phase68.progress import md_table, write_json, write_text
from phase68.security import security_audit
from phase68.statistics import statistical_reliability
from phase68.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase68.tests.test_phase68")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase67.tests.test_phase67",
        "phase66.tests.test_phase66",
        "phase12.tests.test_phase12b",
    ]
    details = []
    ok = True
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for name in suites:
        print(f"regression {name}", flush=True)
        proc = subprocess.run([sys.executable, "-m", "unittest", name, "-q"], capture_output=True, text=True, env=env)
        suite_ok = proc.returncode == 0
        details.append({"suite": name, "ok": suite_ok, "returncode": proc.returncode})
        ok = ok and suite_ok
    return {"ok": ok, "details": details}


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("extract_events", flush=True)
    bundle = extract_events()
    # Persist events without huge path arrays in md — keep full in json with trimmed paths for size
    slim_events = []
    for e in bundle["events"]:
        ee = dict(e)
        outs = {}
        for h, o in e["outcomes"].items():
            oo = {k: v for k, v in o.items() if k != "path_close_moves"}
            outs[h] = oo
        ee["outcomes"] = outs
        slim_events.append(ee)
    bundle_slim = {**bundle, "events": slim_events}
    write_json(REPORTS_DIR / "displacement_events.json", bundle_slim)

    print("displacement_report", flush=True)
    disp = build_displacement_report(bundle)
    write_json(REPORTS_DIR / "displacement_response.json", disp)

    print("competing", flush=True)
    comp = competing_outcomes_report(bundle)
    write_json(REPORTS_DIR / "competing_outcomes.json", comp)

    print("statistics", flush=True)
    stats = statistical_reliability(bundle)
    write_json(REPORTS_DIR / "statistical_reliability.json", stats)

    print("live_integrity", flush=True)
    live = audit_live_evidence()
    write_json(REPORTS_DIR / "live_evidence_integrity.json", live)

    live_spreads = []
    # pull from classified quotes in journal via live audit path
    from phase68.constants import PHASE67_JOURNAL
    import json as _json

    ep = PHASE67_JOURNAL / "events.jsonl"
    if ep.is_file():
        for line in ep.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = _json.loads(line)
            if r.get("kind") == "QUOTE_SNAPSHOT" and r.get("spread") is not None:
                live_spreads.append(float(r["spread"]))

    print("execution", flush=True)
    exe = execution_realism(bundle, live_spreads=live_spreads)
    write_json(REPORTS_DIR / "execution_realism.json", exe)

    print("security/integrity/adversarial/tests", flush=True)
    sec = security_audit()
    integ = audit_integrity()
    adv = run_adversarial_tests()
    tests = _run_tests()
    regs = _run_regressions()
    write_json(REPORTS_DIR / "security_audit.json", sec)
    write_json(REPORTS_DIR / "integrity.json", integ)
    write_json(REPORTS_DIR / "adversarial.json", adv)
    write_json(REPORTS_DIR / "unit_tests.json", tests)
    write_json(REPORTS_DIR / "regressions.json", regs)

    verdict = choose_verdict(
        n_events=bundle["n_events"],
        n_dates=bundle["n_independent_dates"],
        live_integrity_ok=bool(live.get("integrity_verified")),
        security_ok=bool(sec.get("pass")) and bool(integ.get("checks_pass")) and bool(tests.get("ok")),
        exploratory_complete=True,
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    # --- Markdown ---
    write_text(
        REPORTS_DIR / "DISPLACEMENT_RESPONSE_ANALYSIS.md",
        "\n".join(
            [
                "# Displacement Response Analysis",
                "",
                f"- Generated: `{now}`",
                f"- Purpose: `{disp['purpose']}`",
                f"- Definition: `{bundle['definition']}`",
                f"- Stride: `{bundle['event_stride']}` | Horizons: `{bundle['horizons']}`",
                f"- n_events=`{bundle['n_events']}` n_dates=`{bundle['n_independent_dates']}`",
                f"- Holdout accessed: `False` | Independent discovery: `False`",
                f"- Thresholds optimized: `False`",
                "",
                f"## Session caveat",
                disp["session_caveat"],
                "",
                "## By horizon (ALL / BUY / SELL)",
                *[
                    f"### H{h}\n"
                    f"- ALL: `{disp['by_horizon'][h]['ALL']}`\n"
                    f"- BUY: `{disp['by_horizon'][h]['BUY']}`\n"
                    f"- SELL: `{disp['by_horizon'][h]['SELL']}`\n"
                    for h in bundle["horizons"]
                ],
                "## By volatility regime (h12)",
                f"- low: `{disp['by_vol_regime_h12']['low']}`",
                f"- mid: `{disp['by_vol_regime_h12']['mid']}`",
                f"- high: `{disp['by_vol_regime_h12']['high']}`",
                f"- ATR tercile cutoffs: low≤`{bundle['atr_low_threshold']}` high≥`{bundle['atr_high_threshold']}`",
                "",
                "## By session proxy (h12)",
                *[f"- `{s}`: `{disp['by_session_h12'][s]}`" for s in sorted(disp["by_session_h12"])],
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "COMPETING_OUTCOMES_REPORT.md",
        "\n".join(
            [
                "# Competing Outcomes Report",
                "",
                comp["note"],
                "",
                f"- Unique events N=`{comp['n_unique_events']}` dates=`{comp['n_independent_dates']}`",
                f"- Path shape counts: `{comp['path_shape_counts']}`",
                f"- Horizon flip counts: `{comp['horizon_flip_counts']}`",
                f"- By direction terminal h12: `{comp['by_direction_terminal_h12']}`",
                f"- End-return ATR distributions: `{comp['end_return_atr_distributions_h12']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "STATISTICAL_RELIABILITY.md",
        "\n".join(
            [
                "# Statistical Reliability",
                "",
                f"- Event count: `{stats['event_count']}`",
                f"- Independent date count: `{stats['independent_date_count']}`",
                f"- Events/date: `{stats['events_per_date']}`",
                f"- Date-level p_cont variability: `{stats['date_level_variability_p_cont_h12']}`",
                f"- BUY n=`{stats['buy_n']}` SELL n=`{stats['sell_n']}`",
                "",
                "## Date-block bootstrap (h12)",
                *[f"- `{k}`: `{v}`" for k, v in stats["bootstrap_h12"].items()],
                "",
                f"## Dependence",
                stats["event_overlap_dependence"],
                "",
                f"## Censoring",
                f"`{stats['missing_censoring']}`",
                "",
                f"- Significance claimed: `{stats['significance_claim']}`",
                f"- {stats['significance_note']}",
                "",
                "## Date-level table (excerpt)",
                md_table(stats["date_level_rows"][:15], ["day", "n_events", "n_ok_h12", "p_cont_h12", "p_rev_h12", "mean_end_atr_h12"]),
                "",
                f"(full rows in statistical_reliability.json; n_dates=`{stats['independent_date_count']}`)",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "EXECUTION_REALISM.md",
        "\n".join(
            [
                "# Execution Realism",
                "",
                f"- Historical: `{exe['historical_broker']}` `{exe['historical_symbol']}`",
                f"- Live: `{exe['live_broker']}` `{exe['live_symbol']}`",
                f"- Exact historical executable returns claimed: `{exe['exact_historical_executable_returns_claimed']}`",
                f"- Reason: {exe['reason']}",
                "",
                f"## Gross price movement |h12|",
                f"`{exe['gross_price_movement_h12_abs']}`",
                "",
                f"## Spread evidence",
                f"`{exe['available_spread_evidence']}`",
                "",
                "## Cost sensitivity (ASSUMPTIONS — not measured Exness all-in costs)",
                md_table(
                    exe["cost_sensitivity_scenarios"],
                    [
                        "assumed_roundtrip_spread_price_units",
                        "label",
                        "mean_abs_gross_h12",
                        "fraction_events_gross_exceeds_assumed_spread",
                        "commission",
                        "swap",
                        "slippage",
                    ],
                ),
                "",
                exe["break_even_note"],
                f"- Unknown costs zeroed: `{exe['unknown_costs_zeroed']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "LIVE_EVIDENCE_INTEGRITY.md",
        "\n".join(
            [
                "# Live Evidence Integrity",
                "",
                f"- Journal: `{live['journal_path']}`",
                f"- Records: `{live['n_records']}`",
                f"- Provenance counts: `{live['provenance_counts']}`",
                f"- Historical init backfill M5: `{live['historical_init_backfill_m5']}`",
                f"- Newly observed live closed M5: `{live['newly_observed_live_closed_m5']}`",
                f"- Live quote observations: `{live['live_quote_observations']}`",
                f"- Synthetic fixtures: `{live['synthetic_fixtures']}`",
                f"- Independent dates: `{live['independent_dates']}`",
                f"- Wall-clock runtime_sec measured: `{live['wall_clock_runtime_sec_measured']}`",
                f"- Started/ended: `{live['collector_started_utc']}` → `{live['collector_ended_utc']}`",
                f"- Reconnects observed: `{live['reconnects_observed']}`",
                f"- Gaps: `{live['collection_gaps']}`",
                "",
                "## Demonstration: backfill ≠ newly observed",
                f"`{live['demonstration']}`",
                "",
                f"- Continuous uptime claimed: `{live['continuous_uptime_claimed']}`",
                f"- Integrity verified: `{live['integrity_verified']}`",
                f"- Failure reasons: `{live['integrity_failure_reasons']}`",
                f"- Unapproved tick API hits: `{live['unapproved_tick_api_hits_in_phase67_runtime_code']}`",
                "",
            ]
        ),
    )

    elapsed = time.perf_counter() - t0
    write_text(
        REPORTS_DIR / "PHASE68_FINAL_REPORT.md",
        "\n".join(
            [
                "# Phase 68 — Final Report",
                "",
                f"- Generated: `{now}`",
                f"- Recipe: `{RECIPE_ID}`",
                f"- Elapsed sec: `{elapsed:.1f}`",
                f"- **Primary verdict: `{verdict['verdict']}`**",
                f"- Secondary: `{verdict['secondary_verdicts']}`",
                f"- Reason: {verdict['reason']}",
                "",
                "## Distinctions",
                f"- Exploratory behaviour identified eligible: see primary/secondary",
                f"- Live collection integrity verified: `{verdict['live_collection_integrity_verified']}`",
                f"- Independent discovery: `{verdict['independent_discovery']}`",
                f"- Champion promotion: `{verdict['champion_promotion']}`",
                "",
                "## Key counts",
                f"- Displacement events: `{bundle['n_events']}` on `{bundle['n_independent_dates']}` dates",
                f"- Live backfill M5 / newly closed M5 / quotes: "
                f"`{live['historical_init_backfill_m5']}` / `{live['newly_observed_live_closed_m5']}` / `{live['live_quote_observations']}`",
                "",
                "## Tests",
                f"- Unit `{tests['ok']}` adversarial `{adv['suite_pass']}` regressions `{regs['ok']}` security `{sec['pass']}`",
                "",
                "## Invariants",
                md_table([{"k": k, "v": v} for k, v in verdict["invariants"].items()], ["k", "v"]),
                "",
                f"Champion `{CHAMPION_STATUS}` Production `{PRODUCTION_FINAL_ACTION}` Live `{LIVE_TRADING}` "
                f"AutomatedOrders `{AUTOMATED_ORDERS}` order_send `{ORDER_SEND}` Collection `{BROKER_COLLECTION}`",
                "",
            ]
        ),
    )

    write_text(
        DOCS_DIR / "PHASE68_STATUS.md",
        f"# Phase 68 Status\n\n- Verdict: `{verdict['verdict']}`\n- Secondary: `{verdict['secondary_verdicts']}`\n",
    )

    print(f"VERDICT {verdict['verdict']}", flush=True)
    print(f"secondary {verdict['secondary_verdicts']}", flush=True)
    print(f"elapsed {elapsed:.1f}s", flush=True)
    return 0 if tests["ok"] and regs["ok"] and sec["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
