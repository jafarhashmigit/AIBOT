"""Phase 64 runner — decision-to-execution readiness audit; CLI only; no broker orders."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase54.decision import NullPolicy
from phase64.adversarial import run_adversarial_tests
from phase64.constants import (
    AUTOMATED_ORDERS,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    file_sha256,
)
from phase64.crash_recovery import run_crash_recovery_suite
from phase64.evidence_integrity import audit_evidence_batch
from phase64.integrity import audit_integrity
from phase64.lifecycle_audit import audit_lifecycle
from phase64.linkage import audit_traceability
from phase64.execution_intent import ExecutionIntentJournal, create_execution_intent
from phase64.progress import write_json, write_text
from phase64.verdict import choose_verdict
import tempfile
from pathlib import Path


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64.tests.test_phase64")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64.tests.test_phase64",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _demo_scaffold_trace() -> dict[str, Any]:
    """Exercise scaffold in an isolated temp journal (not genuine broker evidence)."""
    with tempfile.TemporaryDirectory() as td:
        j = ExecutionIntentJournal(Path(td))
        d = {
            "decision_id": "phase64_scaffold_demo_decision",
            "timestamp_utc": "2026-11-11T12:00:00Z",
            "action": "WAIT",
            "proposed_action": "WAIT",
            "instrument": "XAUUSDm",
            "observation_id": "obs_scaffold",
            "market_state_id": "XAUUSDm:M5:2026-11-11T12:00:00Z",
            "execution_assumptions": {"bid_ref": 2650.1, "ask_ref": 2650.2, "commission": None, "slippage": None},
        }
        create_execution_intent(
            j,
            decision=d,
            risk={"allowed": True, "final_action": "WAIT", "reasons": ["NO_MODEL"]},
            account_profile={"symbol": "XAUUSDm", "environment": "DEMO", "fixture": True},
        )
        return audit_traceability(j)


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("lifecycle_audit", flush=True)
    lifecycle = audit_lifecycle()
    write_json(REPORTS_DIR / "lifecycle_stage_matrix.json", lifecycle)

    print("crash_recovery_suite", flush=True)
    crash = run_crash_recovery_suite()
    write_json(REPORTS_DIR / "crash_recovery_results.json", crash)

    print("evidence_integrity_fixtures", flush=True)
    evidence = audit_evidence_batch(
        [
            {
                "side": "BUY",
                "requested_price": 2650.25,
                "actual_fill_price": 2650.30,
                "bid_at_decision": 2650.10,
                "ask_at_decision": 2650.25,
                "bid_at_exec": 2650.12,
                "ask_at_exec": 2650.30,
                "commission": None,
                "fee": None,
                "swap": None,
                "latency_ms": None,
            },
            {
                "side": "SELL",
                "requested_price": None,
                "actual_fill_price": 2650.00,
                "commission": None,
                "fee": None,
                "swap": None,
            },
        ]
    )
    write_json(REPORTS_DIR / "evidence_integrity_audit.json", evidence)

    print("traceability_scaffold", flush=True)
    trace = _demo_scaffold_trace()
    write_json(REPORTS_DIR / "traceability_coverage.json", trace)

    print("adversarial", flush=True)
    adv = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_audit.json", adv)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", tests)

    null_ok = NullPolicy().version == EXPECTED_NULL_POLICY
    verdict, reason = choose_verdict(
        lifecycle=lifecycle,
        crash_suite=crash,
        traceability=trace,
        integrity=integrity,
        tests_ok=bool(tests.get("ok")) and bool(adv.get("pass")),
        null_ok=null_ok,
        genuine_broker_fills=0,
    )

    validation = {
        "recipe_id": RECIPE_ID,
        "generated_utc": now,
        "verdict": verdict,
        "reason": reason,
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "live": LIVE_TRADING,
        "automated_orders": AUTOMATED_ORDERS,
        "demo_collection": DEMO_COLLECTION,
        "null_policy_ok": null_ok,
        "tests_ok": tests.get("ok"),
        "adversarial_ok": adv.get("pass"),
        "crash_suite_ok": crash.get("suite_pass"),
        "integrity_ok": integrity.get("checks_pass"),
        "broker_execution_ready": False,
        "genuine_broker_evidence": False,
        "phase65_started": False,
    }
    artifacts = [
        "lifecycle_stage_matrix.json",
        "crash_recovery_results.json",
        "evidence_integrity_audit.json",
        "traceability_coverage.json",
        "adversarial_audit.json",
        "phase_integrity_audit.json",
        "test_results.json",
    ]
    validation["artifact_sha256"] = {name: file_sha256(REPORTS_DIR / name) for name in artifacts}
    write_json(REPORTS_DIR / "validation_results.json", validation)

    defects_high = [
        "FUTURE_BROKER_ORDER stage MISSING / NOT_AUTHORIZED — no order_send",
        "EXECUTION_INTENT scaffold exists in Phase64 only — not wired into phase54/56 production lifecycle",
        "No genuine XAUUSDm demo fills linked to paper decision_id",
        "Evidence sufficiency gates unmet (0 linked independent broker-linked decisions)",
    ]
    defects_medium = [
        "MARKET_SNAPSHOT not a first-class persisted artifact",
        "phase6 vs phase54 decision ID semantics inconsistent (deterministic vs UUID)",
        "Commission/fee/swap/latency remain UNKNOWN without genuine broker records",
        "Rejected/cancelled/expired paths tested with fixtures only (broker path NOT_TESTED)",
    ]
    defects_low = [
        "Intent journal not yet integrated with phase57_1 durable experience journal",
        "Account-profile identity on intents still fixture/user-reported",
    ]

    md = [
        "# Phase 64 — Final Report",
        "",
        f"**Recipe:** `{RECIPE_ID}`",
        f"**Verdict:** `{verdict}`",
        f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
        f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Demo Collection:** `{DEMO_COLLECTION}`",
        f"**Broker execution ready:** `False` (do not claim readiness without genuine broker evidence)",
        f"**Reason:** {reason}",
        f"**Generated:** `{now}`",
        "",
        "## Lifecycle stage-by-stage status",
    ]
    for stage in lifecycle.get("lifecycle_order") or []:
        info = (lifecycle.get("stages") or {}).get(stage) or {}
        md.append(f"- **{stage}**: `{info.get('status')}` — {info.get('notes')}")
    md += [
        "",
        f"- Exists: `{(lifecycle.get('summary') or {}).get('exists')}`",
        f"- Partial: `{(lifecycle.get('summary') or {}).get('partial')}`",
        f"- Missing: `{(lifecycle.get('summary') or {}).get('missing')}`",
        "",
        "## Existing versus missing capabilities",
        "- Paper path OBSERVATION→DECISION→RISK→PAPER_ENTRY→OUTCOME→EXPERIENCE: **EXISTS**",
        "- Execution-intent journal (Phase64 scaffold): **PARTIAL** (not production-wired)",
        "- Future broker order submission: **MISSING** / **NOT_TESTED** / **DISABLED**",
        "- Genuine Exness demo deal import: **PARTIAL** (Phase62/63; empty history audited in Phase63)",
        "- Decision↔order↔deal linkage on genuine evidence: **MISSING**",
        "",
        "## Decision-to-order-to-deal traceability",
        f"- Scaffold coverage: `{trace.get('coverage')}`",
        f"- Independent decision rule: partial fills do not inflate counts — `{ (trace.get('independent_decisions') or {}).get('partial_fills_do_not_inflate_decisions') }`",
        f"- Genuine broker orders linked: `{trace.get('genuine_broker_orders_linked')}`",
        f"- Production lifecycle wired: `{trace.get('production_lifecycle_wired')}`",
        "",
        "## Crash / recovery results",
        f"- Suite pass: `{crash.get('suite_pass')}` (`{crash.get('n_pass')}`/`{crash.get('n_cases')}`)",
        f"- Cases: `{[c.get('case') for c in (crash.get('cases') or [])]}`",
        f"- Genuine broker fabricated: `{crash.get('genuine_broker_evidence_fabricated')}`",
        "",
        "## Tests",
        f"- Unit: OK=`{tests.get('ok')}` run=`{tests.get('tests_run')}` fail=`{tests.get('failures')}` err=`{tests.get('errors')}`",
        f"- Adversarial pass: `{adv.get('pass')}`",
        "",
        "## Phase 0–63 immutability",
        f"- Source modified: `{integrity.get('phase0_63_source_modified')}`",
        f"- Phase61/62/63 reports present: `{integrity.get('phase61_report_present')}` / `{integrity.get('phase62_report_present')}` / `{integrity.get('phase63_report_present')}`",
        f"- Allowlist expanded: `{integrity.get('allowlist_expanded')}`",
        f"- Stores merged: `{integrity.get('stores_merged')}`",
        f"- Phase58 holdout sealed: `{integrity.get('phase58_holdout_sealed')}` used=`{integrity.get('phase58_used')}`",
        f"- order_send prohibited: `{integrity.get('order_send_prohibited')}`",
        "",
        "## Artifact SHA-256",
    ]
    for name, h in (validation.get("artifact_sha256") or {}).items():
        md.append(f"- `{name}`: `{h}`")
    md += [
        "",
        "## Remaining defects",
        "### High",
    ]
    md.extend(f"- {d}" for d in defects_high)
    md.append("### Medium")
    md.extend(f"- {d}" for d in defects_medium)
    md.append("### Low")
    md.extend(f"- {d}" for d in defects_low)
    md += [
        "",
        "## Next recommended engineering action",
        "1. Keep Automated Orders DISABLED; do not enable `order_send`.",
        "2. After genuine XAUUSDm demo trades exist, export History→Deals CSV and import via Phase63.",
        "3. Design a production wiring RFC: phase54/56 decision → Phase64 intent journal → (future) manual/demo order record linkage — still no auto-trading.",
        "4. Do not start Phase65 until this readiness audit is accepted and genuine linked fills begin accumulating.",
        "5. Keep Champion NO_MODEL / Production WAIT / Live NOT_AUTHORIZED.",
        "",
        "## Commands",
        "```powershell",
        "$env:PYTHONPATH='src'",
        ".\\.venv\\Scripts\\python.exe -m phase64.run_phase64",
        ".\\.venv\\Scripts\\python.exe -m unittest phase64.tests.test_phase64 phase63.tests.test_phase63 phase62.tests.test_phase62 phase61.tests.test_phase61",
        "```",
        "",
        f"Runtime s: `{time.perf_counter() - t0}`",
        "",
    ]
    write_text(REPORTS_DIR / "PHASE64_FINAL_REPORT.md", "\n".join(md))
    write_text(
        DOCS_DIR / "PHASE_64_DEMO_DECISION_EXECUTION_READINESS.md",
        "Phase 64 readiness audit. See `reports/phase64/PHASE64_FINAL_REPORT.md`.\n",
    )

    print(f"VERDICT={verdict}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_FINAL_REPORT.md'}", flush=True)
    return 0 if tests.get("ok") and adv.get("pass") and crash.get("suite_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
