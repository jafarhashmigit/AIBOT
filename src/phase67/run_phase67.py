"""Phase 67 runner — Exness collection ops + exploratory research."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_5.journal import BrokerEvidenceJournal
from phase67.adversarial import run_adversarial_tests
from phase67.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COST_MODEL_INCOMPLETE,
    DEFAULT_VERIFY_RUNTIME_SEC,
    DOCS_DIR,
    EXECUTION_AUTHORIZATION,
    GENUINE_FILLS,
    JOURNAL_ROOT,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    UNAPPROVED,
)
from phase67.exploratory import run_exploratory_analysis
from phase67.hypotheses import future_hypothesis_candidates
from phase67.integrity import audit_integrity
from phase67.progress import md_table, write_json, write_text
from phase67.security import security_audit
from phase67.service import health_check, verify_runtime
from phase67.tick_api_audit import audit_tick_api_approval
from phase67.transferability import compare_broker_substrates
from phase67.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase67.tests.test_phase67")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase66.tests.test_phase66",
        "phase64_13.tests.test_phase64_13",
        "phase64_9.tests.test_phase64_9",
        "phase12.tests.test_phase12b",
    ]
    details = []
    ok = True
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for name in suites:
        print(f"regression {name}", flush=True)
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", name, "-q"],
            capture_output=True,
            text=True,
            env=env,
        )
        suite_ok = proc.returncode == 0
        details.append({"suite": name, "ok": suite_ok, "returncode": proc.returncode, "stderr_tail": (proc.stderr or "")[-400:]})
        ok = ok and suite_ok
    return {"ok": ok, "details": details}


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("tick_api_audit", flush=True)
    tick = audit_tick_api_approval()
    write_json(REPORTS_DIR / "tick_api_audit.json", tick)

    print("security", flush=True)
    sec = security_audit()
    write_json(REPORTS_DIR / "security_audit.json", sec)

    print("integrity", flush=True)
    integ = audit_integrity()
    write_json(REPORTS_DIR / "integrity.json", integ)

    print("verify_runtime", flush=True)
    verify = verify_runtime(duration_sec=float(DEFAULT_VERIFY_RUNTIME_SEC), interval_sec=20.0)
    write_json(REPORTS_DIR / "verify_runtime.json", verify)

    print("health", flush=True)
    health = health_check()
    write_json(REPORTS_DIR / "collection_health.json", health)

    print("exploratory", flush=True)
    explor = run_exploratory_analysis()
    write_json(REPORTS_DIR / "exploratory_analysis.json", explor)

    print("transferability", flush=True)
    xfer = compare_broker_substrates()
    write_json(REPORTS_DIR / "broker_transferability.json", xfer)

    print("hypotheses", flush=True)
    hyps = future_hypothesis_candidates()
    write_json(REPORTS_DIR / "future_hypotheses.json", hyps)

    print("adversarial", flush=True)
    adv = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial.json", adv)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "unit_tests.json", tests)

    print("regressions", flush=True)
    regs = _run_regressions()
    write_json(REPORTS_DIR / "regressions.json", regs)

    journal = BrokerEvidenceJournal(JOURNAL_ROOT, allow_synthetic=False, store_label="GENUINE")
    events = journal.all_events()
    quotes = [e for e in events if e.get("kind") == "QUOTE_SNAPSHOT"]
    m5s = [e for e in events if e.get("kind") == "M5_BAR"]
    dates = sorted({str(e.get("server_timestamp_utc") or "")[:10] for e in events if e.get("server_timestamp_utc")})

    verdict = choose_verdict(
        security_ok=bool(sec.get("pass")),
        integrity_ok=bool(integ.get("checks_pass")),
        exploratory_ok=bool(explor.get("n_independent_dates", 0) >= 40 and explor.get("holdout_accessed") is False),
        ops_design_ok=True,
        verify_runtime=verify,
        live_dates=len(dates),
        live_m5=len(m5s),
        live_quotes=len(quotes),
        tests_ok=bool(tests.get("ok")) and bool(adv.get("suite_pass")) and bool(regs.get("ok")),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    # --- Markdown reports ---
    write_text(
        REPORTS_DIR / "TICK_API_APPROVAL_AUDIT.md",
        "\n".join(
            [
                "# Tick API Approval Audit",
                "",
                f"- Any tick API approved: `{tick['any_tick_api_approved']}`",
                f"- Phase67 uses ticks: `{tick['phase67_uses_ticks']}`",
                "",
                md_table(tick["tick_candidates"], ["api", "in_permitted", "in_prohibited", "status", "safe_to_call_in_phase67", "reason"]),
                "",
                "## Approval requirement",
                tick["approval_requirement"],
                "",
                f"- Permitted market APIs: `{tick['permitted_market_apis']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "COLLECTION_OPERATIONAL_DESIGN.md",
        "\n".join(
            [
                "# Collection Operational Design",
                "",
                "- Reuses Phase66 `collect_once` + Phase64.5 `BrokerEvidenceJournal`.",
                "- APIs: `symbol_info` (bid/ask/time), `copy_rates_from_pos` (M5 lookback), `account_info`, `terminal_info`.",
                "- Tick stream: **not used** (not Phase12-permitted).",
                "- Fail-closed: wrong symbol/server/account; disconnect suspends cycle as BLOCKED.",
                "- Dedup via journal stable_key; watermark for lag; quarantine rejects.",
                "- Session labeling via Phase64.13; market-closed ≠ collector failure.",
                "- Synthetic fixtures never enter genuine journal (`allow_synthetic=False`).",
                f"- Service version loop writes PID/state/log under `src/data/phase67/service/`.",
                f"- Verify measured runtime_sec=`{verify.get('runtime_sec_measured')}` ingested=`{(verify.get('totals') or {}).get('INGESTED')}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "COLLECTION_RUNTIME_GUIDE.md",
        "\n".join(
            [
                "# Collection Runtime Guide (Windows)",
                "",
                "Prerequisites: MetaTrader 5 connected to Exness-MT5Trial15 with XAUUSDm visible; project venv.",
                "",
                "## Start (background)",
                "```powershell",
                "cd C:\\Users\\Dell\\Documents\\1\\AIBOT",
                "$env:PYTHONPATH='src'",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli start --interval 30 --m5-lookback 50",
                "```",
                "",
                "## Start (foreground)",
                "```powershell",
                "$env:PYTHONPATH='src'",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli run --interval 30 --m5-lookback 50",
                "```",
                "",
                "## Stop",
                "```powershell",
                "$env:PYTHONPATH='src'",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli stop",
                "```",
                "",
                "## Health-check",
                "```powershell",
                "$env:PYTHONPATH='src'",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli health",
                "```",
                "",
                "## Bounded verify (measured runtime)",
                "```powershell",
                "$env:PYTHONPATH='src'",
                ".\\.venv\\Scripts\\python.exe -m phase67.cli verify --duration 90 --interval 20",
                "```",
                "",
                "## Safe restart",
                "1. `python -m phase67.cli stop`",
                "2. Confirm health shows STOPPED / no live PID",
                "3. `python -m phase67.cli start ...`",
                "4. Dedup index prevents duplicate evidence on overlapping M5/quotes",
                "",
                "## Paths",
                "- Journal: `src/data/phase67/exness_market_evidence_journal/`",
                "- Logs: `src/data/phase67/service/collector.log`",
                "- PID/state: `src/data/phase67/service/collector.pid` / `collector_state.json`",
                "",
                "Do not claim continuous uptime from unit tests alone.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "EXNESS_EVIDENCE_REPORT.md",
        "\n".join(
            [
                "# Exness Evidence Report",
                "",
                f"- Generated: `{now}`",
                f"- Journal events: `{len(events)}` quotes=`{len(quotes)}` m5=`{len(m5s)}`",
                f"- Independent dates: `{dates}`",
                f"- Verify runtime_sec_measured: `{verify.get('runtime_sec_measured')}`",
                f"- Verify totals: `{verify.get('totals')}`",
                f"- Continuous uptime claimed: `False`",
                f"- Tick stream observations: `0` (API not approved)",
                f"- Source classification: `BROKER_OBSERVED` when live path succeeds",
                f"- Integrity: `{journal.integrity_report()}`",
                "",
                "## Honesty",
                "Counts above are from persisted journal files after the Phase67 verify run. "
                "They do not constitute long-horizon operational reliability.",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "HISTORICAL_EXPLORATORY_ANALYSIS.md",
        "\n".join(
            [
                "# Historical Exploratory Analysis",
                "",
                f"- Purpose: `{explor['purpose']}`",
                f"- Independent discovery/validation/confirmation: `False`",
                f"- Holdout accessed: `{explor['holdout_accessed']}`",
                f"- Thresholds optimized for profit: `{explor['thresholds_optimized_for_profit']}`",
                f"- Independent dates analyzed: `{explor['n_independent_dates']}`",
                f"- Fixed thresholds: `{explor['fixed_thresholds']}`",
                "",
                "## Definitions",
                *[f"- **{k}**: {v}" for k, v in explor["definitions"].items()],
                "",
                "## A. Failed breakout (descriptive)",
                f"- n_events=`{explor['failed_breakout']['n_events']}` dates=`{explor['failed_breakout']['n_independent_dates']}`",
                f"- by_session=`{explor['failed_breakout']['by_session_counts']}`",
                f"- by_direction means (excerpt): `{explor['failed_breakout']['by_direction']}`",
                "",
                "## B. Volatility-conditioned continuation",
                f"- low=`{explor['volatility_conditioned_continuation']['low_vol']['n_events']}` "
                f"mid=`{explor['volatility_conditioned_continuation']['mid_vol']['n_events']}` "
                f"high=`{explor['volatility_conditioned_continuation']['high_vol']['n_events']}`",
                f"- ATR thresholds low/high: `{explor['volatility_conditioned_continuation']['atr_low_threshold']}` / "
                f"`{explor['volatility_conditioned_continuation']['atr_high_threshold']}`",
                "",
                "## C. Mean reversion after displacement",
                f"- reversion summary n=`{explor['mean_reversion_after_displacement']['reversion_path']['n_events']}`",
                f"- continuation summary n=`{explor['mean_reversion_after_displacement']['continuation_path']['n_events']}`",
                "",
                "## D/E. Session + directional asymmetry",
                f"- `{explor['directional_asymmetry_h12']}`",
                "",
                "## Limitations",
                *[f"- {n}" for n in explor["inconclusive_notes"]],
                f"- {explor['cost_note']}",
                "",
                "**These results are descriptive only — not predictive confirmation.**",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "BROKER_DATA_TRANSFERABILITY.md",
        "\n".join(
            [
                "# Broker Data Transferability",
                "",
                md_table(xfer["differences"], ["aspect", "historical", "live", "identical"]),
                "",
                f"- Execution characteristics assumed identical: `{xfer['execution_characteristics_assumed_identical']}`",
                f"- Historical may inform hypothesis design: `{xfer['historical_may_inform_hypothesis_design']}`",
                f"- Exness validation requires new Exness observations: `{xfer['exness_validation_requires_new_exness_observations']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "FUTURE_HYPOTHESIS_CANDIDATES.md",
        "\n".join(
            [
                "# Future Hypothesis Candidates",
                "",
                f"- Ranking basis: `{hyps['ranking_basis']}`",
                f"- Confirmatory tests run: `{hyps['confirmatory_tests_run']}`",
                "",
                *[
                    "\n".join(
                        [
                            f"## {c['rank']}. `{c['id']}`",
                            f"- Rationale: {c['economic_rationale']}",
                            f"- Definition: {c['definition']}",
                            f"- Features: {c['required_features']}",
                            f"- Data availability: {c['data_availability']}",
                            f"- Expected frequency: {c['expected_event_frequency']}",
                            f"- Entry/exit: {c['entry_exit']}",
                            f"- BUY/SELL/WAIT: {c['buy_sell_wait']}",
                            f"- Failures: {c['main_failure_conditions']}",
                            f"- Costs: {c['cost_dependencies']}",
                            f"- Required sample: {c['required_independent_sample']}",
                            f"- Preregistration: {c['preregistration']}",
                            "",
                        ]
                    )
                    for c in hyps["candidates"]
                ],
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "SECURITY_AUDIT.md",
        "\n".join(
            [
                "# Security Audit",
                "",
                f"- Pass: `{sec['pass']}`",
                f"- order_send call sites: `{sec['order_send_call_sites']}`",
                f"- Unapproved API hits: `{sec['unapproved_api_hits']}`",
                f"- Tick APIs called: `{sec['tick_apis_called']}`",
                f"- Submission/execution: `{sec['submission_enabled']}` / `{sec['execution_authorized']}`",
                f"- Holdout outcomes accessed: `{sec['holdout_outcomes_accessed']}`",
                f"- Integrity checks: `{integ['checks_pass']}`",
                "",
            ]
        ),
    )

    write_text(
        REPORTS_DIR / "TEST_RESULTS.md",
        "\n".join(
            [
                "# Test Results",
                "",
                f"- Unit ok=`{tests['ok']}` run=`{tests['tests_run']}` fail=`{tests['failures']}` err=`{tests['errors']}`",
                f"- Adversarial ok=`{adv['suite_pass']}` ({adv['n_pass']}/{adv['n_cases']})",
                f"- Regressions ok=`{regs['ok']}`",
                "",
                md_table(regs["details"], ["suite", "ok", "returncode"]),
                "",
                md_table(adv["cases"], ["name", "pass"]),
                "",
            ]
        ),
    )

    elapsed = time.perf_counter() - t0
    write_text(
        REPORTS_DIR / "PHASE67_FINAL_REPORT.md",
        "\n".join(
            [
                "# Phase 67 — Final Report",
                "",
                f"- Generated: `{now}`",
                f"- Recipe: `{RECIPE_ID}`",
                f"- Elapsed sec: `{elapsed:.1f}`",
                f"- **Verdict: `{verdict['verdict']}`**",
                f"- Reason: {verdict['reason']}",
                "",
                "## Engineering vs actual collection",
                f"- Engineering ops ready: `{verdict['engineering_ops_ready']}`",
                f"- Measured verify runtime_sec: `{verdict['measured_verify_runtime_sec']}`",
                f"- Verify ingested: `{verdict['verify_ingested']}`",
                f"- Continuous uptime claimed: `{verdict['continuous_uptime_claimed']}`",
                f"- Live dates/m5/quotes in journal: `{len(dates)}` / `{len(m5s)}` / `{len(quotes)}`",
                f"- Exploratory complete: `{verdict['exploratory_complete']}`",
                f"- Live evidence sufficient for discovery: `{verdict['live_evidence_sufficient_for_discovery']}`",
                "",
                "## Track A summary",
                "- Persistent RO collector service + CLI start/stop/health/verify.",
                "- Tick APIs not approved — documented; not called.",
                "",
                "## Track B summary",
                f"- Exploratory on `{explor['n_independent_dates']}` previously consumed dates; holdout sealed.",
                "- Fixed thresholds; descriptive statistics only; 5 future hypothesis candidates ranked.",
                "",
                "## Invariants",
                md_table([{"k": k, "v": v} for k, v in verdict["invariants"].items()], ["k", "v"]),
                "",
                f"- Champion `{CHAMPION_STATUS}` Production `{PRODUCTION_FINAL_ACTION}` Live `{LIVE_TRADING}` "
                f"AutomatedOrders `{AUTOMATED_ORDERS}` order_send `{ORDER_SEND}` Collection `{BROKER_COLLECTION}` "
                f"Execution `{EXECUTION_AUTHORIZATION}` Risk `{UNAPPROVED}` Cost `{COST_MODEL_INCOMPLETE}` "
                f"Fills `{GENUINE_FILLS}` submit/auth `{BROKER_SUBMISSION_ENABLED}`/`{BROKER_EXECUTION_AUTHORIZED}`",
                "",
            ]
        ),
    )

    write_text(
        DOCS_DIR / "PHASE67_STATUS.md",
        "\n".join(
            [
                "# Phase 67 Status",
                "",
                f"- Verdict: `{verdict['verdict']}`",
                f"- Engineering ops ready: `{verdict['engineering_ops_ready']}`",
                f"- Live discovery-ready: `{verdict['live_evidence_sufficient_for_discovery']}`",
                "",
            ]
        ),
    )

    print(f"VERDICT {verdict['verdict']}", flush=True)
    print(f"elapsed {elapsed:.1f}s", flush=True)
    return 0 if tests["ok"] and regs["ok"] and sec["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
