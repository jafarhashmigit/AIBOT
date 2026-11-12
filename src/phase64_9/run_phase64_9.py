"""Phase 64.9 runner — execution preflight & order_send security (no live orders / no Phase65)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase64_9.adapter import BrokerExecutionAdapter
from phase64_9.adversarial import run_adversarial_tests
from phase64_9.authorization import authorization_model_spec, evaluate_authorization
from phase64_9.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    UNAPPROVED,
)
from phase64_9.fake_broker import run_fake_broker_suite
from phase64_9.integrity import audit_integrity
from phase64_9.intent_fsm import intent_fsm_spec
from phase64_9.path_trace import build_path_trace
from phase64_9.preflight import preflight_spec, run_preflight, PreflightContext, symbol_spec_hash
from phase64_9.progress import write_json, write_text
from phase64_9.recovery import run_recovery_suite
from phase64_9.risk_calc import run_risk_calc_tests
from phase64_9.security_review import build_order_send_security_review
from phase64_9.verdict import choose_verdict
from phase64_9.constants import (
    ACTIVE_SYMBOL,
    EXPECTED_CURRENCY,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_DIGITS,
    VERIFIED_TICK_SIZE,
    VERIFIED_TICK_VALUE,
)
from phase64_9.intent_fsm import ExecutionIntentStore


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_9.tests.test_phase64_9")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_9.tests.test_phase64_9",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_8.tests.test_phase64_8",
        "phase64_7.tests.test_phase64_7",
        "phase64_6.tests.test_phase64_6",
        "phase64_5.tests.test_phase64_5",
        "phase64_4.tests.test_phase64_4",
        "phase12.tests.test_phase12b",
    ]
    details = []
    ok = True
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for name in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", name, "-q"],
            capture_output=True,
            text=True,
            env=env,
        )
        # One retry for rare WAL/tempfile races on Windows
        if proc.returncode != 0:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", name, "-q"],
                capture_output=True,
                text=True,
                env=env,
            )
        suite_ok = proc.returncode == 0
        details.append({"suite": name, "returncode": proc.returncode, "ok": suite_ok, "stderr_tail": (proc.stderr or "")[-400:]})
        ok = ok and suite_ok
    return {"ok": ok, "details": details}


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("path_trace", flush=True)
    path_trace = build_path_trace()
    write_json(REPORTS_DIR / "execution_path_trace.json", path_trace)

    print("security_review", flush=True)
    security = build_order_send_security_review()
    write_json(REPORTS_DIR / "order_send_security_review.json", security)

    print("preflight_spec", flush=True)
    write_json(REPORTS_DIR / "execution_preflight_spec.json", preflight_spec())

    # Demonstrate preflight reject under current UNAPPROVED risk
    s = symbol_spec_hash(
        tick_size=VERIFIED_TICK_SIZE,
        tick_value=VERIFIED_TICK_VALUE,
        contract_size=VERIFIED_CONTRACT_SIZE,
        digits=VERIFIED_DIGITS,
        volume_min=0.01,
        volume_step=0.01,
    )
    demo_pf = run_preflight(
        PreflightContext(
            account_fingerprint="fp",
            expected_fingerprint="fp",
            server=EXPECTED_SERVER,
            currency=EXPECTED_CURRENCY,
            login=EXPECTED_DEMO_LOGIN,
            symbol=ACTIVE_SYMBOL,
            symbol_spec_hash=s,
            expected_symbol_spec_hash=s,
            bid=2649.5,
            ask=2650.0,
            tick_age_sec=1.0,
            trading_session_known=True,
            in_trading_session=True,
            direction="BUY",
            volume=0.01,
            price=2650.0,
            sl=2649.0,
            tp=2652.0,
            filling_mode_bitmask=7,
            requested_filling=1,
            commission=-0.06,
            risk_policy_status=UNAPPROVED,
            decision_id="demo",
            decision_action="BUY",
            execution_intent_id="demo_i",
        )
    )
    write_json(REPORTS_DIR / "preflight_demo_current_policy.json", demo_pf)

    print("intent_fsm", flush=True)
    write_json(REPORTS_DIR / "execution_intent_state_machine.json", intent_fsm_spec())
    with tempfile.TemporaryDirectory() as td:
        store = ExecutionIntentStore(Path(td))
        created = store.create_intent(decision_id="report_d1", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
        dup = store.create_intent(decision_id="report_d1", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
        intent_ok = created["status"] == "CREATED" and dup["status"] == "DUPLICATE_REJECTED"
    write_json(REPORTS_DIR / "intent_idempotency_evidence.json", {"created": created, "duplicate": dup, "pass": intent_ok})

    print("adapter_boundary", flush=True)
    adapter_status = BrokerExecutionAdapter().status()
    blocked = BrokerExecutionAdapter().submit({"intent_id": "probe"})
    write_json(
        REPORTS_DIR / "broker_submission_adapter_boundary.json",
        {"status": adapter_status, "submit_probe": blocked},
    )

    print("fake_broker", flush=True)
    fake = run_fake_broker_suite()
    write_json(REPORTS_DIR / "fake_broker_backend_evidence.json", fake)

    print("recovery", flush=True)
    with tempfile.TemporaryDirectory() as td:
        recovery = run_recovery_suite(Path(td))
    write_json(REPORTS_DIR / "crash_timeout_recovery_evidence.json", recovery)

    print("authorization", flush=True)
    auth = evaluate_authorization()
    write_json(REPORTS_DIR / "authorization_model.json", {"spec": authorization_model_spec(), "evaluation": auth})

    print("risk_calc", flush=True)
    risk = run_risk_calc_tests()
    write_json(REPORTS_DIR / "risk_calculation_tests.json", risk)

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_security_results.json", adversarial)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    write_json(
        REPORTS_DIR / "swap_long_conflict_preserved.json",
        {
            "phase63_user_reported_swap_long": SWAP_LONG_PHASE63,
            "phase64_7_live_swap_long": SWAP_LONG_PHASE64_7,
            "overwrite": False,
            "interchangeable": False,
        },
    )

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", tests)

    print("regressions", flush=True)
    regressions = _run_regressions()
    write_json(REPORTS_DIR / "regression_results.json", regressions)

    remaining = [
        "Risk policy remains UNAPPROVED — preflight rejects under current policy",
        "Commission schedule UNKNOWN — cost completeness incomplete",
        "Trading sessions completeness incomplete for live gate",
        "swap_long conflict preserved (−488.7 vs −644.8); not interchangeable",
        "Genuine trade fill reconciliation not validated (0 trade deals)",
        "BROKER_SUBMISSION_ENABLED=False; order_send PROHIBITED",
        "BROKER_EXECUTION_AUTHORIZED=False; Phase65 NOT_STARTED",
        "No manual trade performed; no real broker order submitted",
    ]
    write_json(REPORTS_DIR / "remaining_blockers.json", {"blockers": remaining})

    verdict = choose_verdict(
        security_review=security,
        path_trace=path_trace,
        preflight_ok=demo_pf["status"] == "PREFLIGHT_REJECTED" and preflight_spec()["fail_closed"],
        intent_ok=intent_ok,
        fake_ok=bool(fake.get("suite_pass")),
        recovery_ok=bool(recovery.get("suite_pass")),
        auth_ok=auth.get("authorized") is False,
        adversarial_ok=bool(adversarial.get("suite_pass")),
        integrity_ok=bool(integrity.get("checks_pass")),
        risk_calc_ok=bool(risk.get("suite_pass")),
        tests_ok=bool(tests.get("ok")),
        regressions_ok=bool(regressions.get("ok")),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    dims = verdict["dimensions"]
    report = "\n".join(
        [
            "# Phase 64.9 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict['verdict']}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Broker Collection:** `{BROKER_COLLECTION}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**order_send:** `{ORDER_SEND}` | **BROKER_SUBMISSION_ENABLED:** `{BROKER_SUBMISSION_ENABLED}`",
            f"**BROKER_EXECUTION_AUTHORIZED:** `{BROKER_EXECUTION_AUTHORIZED}` | **Risk Policy:** `{UNAPPROVED}` | **Phase65:** `{PHASE65}`",
            f"**Reason:** {verdict['reason']}",
            f"**Generated:** `{now}`",
            "",
            "## Dimensions (not conflated)",
            *[f"- {k}: `{v}`" for k, v in dims.items()],
            "",
            "## order_send security",
            f"- Review pass: `{security.get('pass')}` | Enabled: `{security.get('enabled_in_phase64_9')}`",
            f"- Path trace pass: `{path_trace.get('pass')}` | Call sites: `{len(path_trace['order_send']['call_sites_in_src'])}`",
            f"- Adapter submit probe reached_order_send: `{blocked.get('reached_order_send')}`",
            "",
            "## Preflight / intent / recovery",
            f"- Current-policy demo preflight: `{demo_pf.get('status')}` (expected REJECTED while risk UNAPPROVED)",
            f"- Intent idempotency: `{intent_ok}`",
            f"- Fake broker suite: `{fake.get('suite_pass')}` (`{fake.get('n_pass')}`/`{fake.get('n_cases')}`)",
            f"- Recovery suite: `{recovery.get('suite_pass')}` (`{recovery.get('n_pass')}`/`{recovery.get('n_cases')}`)",
            f"- Authorization authorized: `{auth.get('authorized')}`",
            "",
            "## Tests",
            f"- Unit OK=`{tests.get('ok')}` run=`{tests.get('tests_run')}`",
            f"- Adversarial: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
            f"- Risk calc: `{risk.get('suite_pass')}`",
            f"- Regressions OK=`{regressions.get('ok')}`",
            f"- Integrity: `{integrity.get('checks_pass')}`",
            "",
            "## Invariants",
            *[f"- {k}: `{v}`" for k, v in verdict["invariants"].items()],
            f"- not_broker_execution_authorization: `{verdict['not_broker_execution_authorization']}`",
            "",
            "## Remaining blockers",
            *[f"- {b}" for b in remaining],
            "",
            "**Next highest-impact task:** Propose (still non-executing) an explicitly reviewable demo risk-policy "
            "with justified numeric limits and commission handling — do **not** start Phase65 or enable `order_send`.",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_9.run_phase64_9",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_9_FINAL_REPORT.md", report)
    write_text(DOCS_DIR / "PHASE_64_9_ORDER_SUBMISSION_SECURITY_EXECUTION_PREFLIGHT.md", report)

    print(verdict["verdict"], flush=True)
    return 0 if verdict["verdict"] != "EXECUTION_PREFLIGHT_BLOCKED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
