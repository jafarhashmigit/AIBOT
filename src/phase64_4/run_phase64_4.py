"""Phase 64.4 runner — broker demo execution safety design validation (DESIGN-ONLY)."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase64_4.adversarial import run_adversarial_tests
from phase64_4.architecture_audit import audit_existing_architecture
from phase64_4.authorization_gate import (
    conditions_before_demo_execution_review,
    evaluate_authorization,
)
from phase64_4.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    SCHEMA_VERSION,
    STATE_MACHINE_VERSION,
)
from phase64_4.economics import audit_economics, economics_specification
from phase64_4.integrity import audit_integrity
from phase64_4.progress import write_json, write_text
from phase64_4.recovery_design import audit_recovery_design
from phase64_4.risk_spec import audit_risk_spec, risk_control_specification
from phase64_4.schemas import audit_schemas, schema_definitions
from phase64_4.state_machine import audit_state_machine, state_machine_spec
from phase64_4.symbol_verification import audit_symbol_configuration
from phase64_4.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_4.tests.test_phase64_4")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_4.tests.test_phase64_4",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("architecture_audit", flush=True)
    architecture = audit_existing_architecture()
    write_json(REPORTS_DIR / "architecture_integration_audit.json", architecture)

    print("schemas", flush=True)
    schemas = audit_schemas()
    write_json(REPORTS_DIR / "broker_event_schemas.json", schema_definitions())
    write_json(REPORTS_DIR / "schema_validation.json", schemas)

    print("state_machine", flush=True)
    fsm = audit_state_machine()
    write_json(REPORTS_DIR / "state_machine_spec.json", state_machine_spec())
    write_json(REPORTS_DIR / "state_machine_validation.json", fsm)

    print("symbol_verification", flush=True)
    symbol = audit_symbol_configuration()
    write_json(REPORTS_DIR / "xauusdm_verification_checklist.json", symbol)

    print("risk_spec", flush=True)
    risk = audit_risk_spec()
    write_json(REPORTS_DIR / "risk_control_specification.json", risk_control_specification())
    write_json(REPORTS_DIR / "risk_spec_validation.json", risk)

    print("economics", flush=True)
    economics = audit_economics()
    write_json(REPORTS_DIR / "execution_economics_specification.json", economics_specification())
    write_json(REPORTS_DIR / "economics_validation.json", economics)

    print("recovery", flush=True)
    recovery = audit_recovery_design()
    write_json(REPORTS_DIR / "crash_recovery_reconciliation_design.json", recovery)

    print("authorization_gate", flush=True)
    authorization = evaluate_authorization()
    write_json(REPORTS_DIR / "authorization_gate_evaluation.json", authorization)
    write_json(
        REPORTS_DIR / "demo_execution_review_preconditions.json",
        {"conditions": conditions_before_demo_execution_review()},
    )

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_audit.json", adversarial)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    unit_tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", unit_tests)

    bundle = {
        "architecture": architecture,
        "schemas": schemas,
        "state_machine": fsm,
        "symbol": symbol,
        "risk": risk,
        "economics": economics,
        "recovery": recovery,
        "authorization": authorization,
        "adversarial": adversarial,
        "integrity": integrity,
        "unit_tests": unit_tests,
    }
    write_json(REPORTS_DIR / "validation_results.json", bundle)
    verdict, reason = choose_verdict(bundle)

    defects = {
        "high": [
            "No genuine Exness demo fills/orders yet — all broker evidence SIMULATED/DESIGN.",
            "history_deals_get / orders_get remain PROHIBITED; broker discovery interim = manual CSV.",
            "All broker risk numeric limits remain UNCONFIGURED.",
        ],
        "medium": [
            "Symbol metadata still USER_REPORTED; tick size/value/account currency/leverage UNKNOWN.",
            "Execution economics always INCOMPLETE until account-specific costs observed.",
            "Kill switch disengage does not (and must not) create submission path in this phase.",
        ],
        "low": [
            "phase0_64_3_source_modified flag is policy-asserted (Phase64.4 only adds new package).",
            "Human approval scope DEMO_EXECUTION_REVIEW_PENDING is informational until a later phase.",
        ],
    }
    write_json(REPORTS_DIR / "remaining_defects.json", defects)

    changed = [
        "src/phase64_4/** (new)",
        "tests/phase64_4/** (new)",
        "reports/phase64_4/** (new)",
        "docs/agent/PHASE_64_4_BROKER_DEMO_EXECUTION_SAFETY_DESIGN.md (new)",
    ]

    report = "\n".join(
        [
            "# Phase 64.4 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**Broker Execution Ready:** `{BROKER_EXECUTION_READY}`",
            f"**Reason:** {reason}",
            f"**Generated:** `{now}`",
            "",
            "## Design posture",
            "- Phase is **DESIGN-ONLY**: no `order_send`, no allowlist expansion, no broker submission path.",
            f"- Schema version: `{SCHEMA_VERSION}` | FSM: `{STATE_MACHINE_VERSION}`",
            f"- Submission authorized by gate: `{authorization.get('submission_authorized')}`",
            f"- Reached order_send: `False`",
            "",
            "## 1. Architecture audit",
            f"- Pass: `{architecture.get('pass')}`",
            f"- Parallel lifecycle introduced: `{architecture.get('parallel_lifecycle_introduced')}`",
            f"- Integration points: `{len(architecture.get('integration_points') or [])}`",
            f"- Attach point: after hardened intent; paper runtime remains `{architecture.get('approved_paper_factory')}`",
            "",
            "## 2. Canonical broker event schemas",
            f"- Pass: `{schemas.get('pass')}` rejects superseded XAUUSD: `{schemas.get('rejects_xauusd')}`",
            "- Events: REQUEST → SUBMISSION → ACK → DEAL → FILL / REJECTION / CANCELLATION / RECONCILIATION",
            "- Linkage: `canonical_decision_id → intent_id → execution_request_id → broker_order_id → broker_deal_id → fill_id`",
            "",
            "## 3. State machine",
            f"- Pass: `{fsm.get('pass')}` timeout→recon: `{fsm.get('timeout_to_recon')}` resubmit blocked: `{fsm.get('resubmit_blocked')}`",
            "",
            "## 4. XAUUSDm verification",
            f"- Pass: `{symbol.get('pass')}` active=`{symbol.get('active_symbol')}`",
            f"- User-reported not independently verified: `{symbol.get('user_reported_not_independently_verified')}`",
            f"- Unknown intact: `{symbol.get('unknown_intact')}` | No XAUUSD fallback: `{symbol.get('no_xauusd_fallback')}`",
            "- RO checklist written to `xauusdm_verification_checklist.json`",
            "",
            "## 5. Risk controls",
            f"- Pass: `{risk.get('pass')}` default blocks when UNCONFIGURED: `{risk.get('unconfigured_blocks_submission')}`",
            "- Numerical limits **not invented**.",
            "",
            "## 6. Execution economics",
            f"- Pass: `{economics.get('pass')}` default total: `{economics.get('default_total')}`",
            "",
            "## 7. Crash recovery / reconciliation",
            f"- Pass: `{recovery.get('pass')}` boundaries covered: `{recovery.get('covers_all_boundaries')}`",
            f"- Runtime crash tests: `{recovery.get('runtime_crash_tests')}`",
            "- Rule: missing local ack ≠ broker rejection.",
            "",
            "## 8. Authorization gate",
            f"- All design gates evaluated; submission_authorized=`{authorization.get('submission_authorized')}`",
            f"- Block reasons (sample): `{(authorization.get('block_reasons') or [])[:5]}`",
            "- Env vars cannot authorize submission.",
            "",
            "## 9. Adversarial",
            f"- Suite pass: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
            f"- Genuine broker evidence: `{adversarial.get('genuine_broker_evidence')}`",
            "",
            "## 10. Tests / immutability",
            f"- Unit: OK=`{unit_tests.get('ok')}` run=`{unit_tests.get('tests_run')}`",
            f"- Integrity checks_pass: `{integrity.get('checks_pass')}`",
            f"- Phase0–64.3 source modified: `{integrity.get('phase0_64_3_source_modified')}`",
            f"- Prior reports present: `{integrity.get('prior_reports_present')}`",
            f"- Allowlist expanded: `{integrity.get('allowlist_expanded')}` | Stores merged: `{integrity.get('stores_merged')}`",
            "",
            "## Changed files",
            *[f"- `{c}`" for c in changed],
            "",
            "## Remaining defects",
            "### High",
            *[f"- {d}" for d in defects["high"]],
            "### Medium",
            *[f"- {d}" for d in defects["medium"]],
            "### Low",
            *[f"- {d}" for d in defects["low"]],
            "",
            "## Conditions before demo-execution authorization review",
            *[f"{i}. {c}" for i, c in enumerate(conditions_before_demo_execution_review(), 1)],
            "",
            "## Next recommended action",
            "1. Perform RO MT5 verification checklist for XAUUSDm; fill UNKNOWN fields from broker facts only.",
            "2. Justify and approve numeric broker risk limits (keep UNCONFIGURED until then).",
            "3. Keep Automated Orders DISABLED; do not expand MT5 allowlist without security review.",
            "4. Do **not** start Phase65; do **not** submit broker orders.",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_4.run_phase64_4",
            ".\\.venv\\Scripts\\python.exe -m unittest phase64_4.tests.test_phase64_4 phase64_3.tests.test_phase64_3",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_4_FINAL_REPORT.md", report)
    write_text(
        DOCS_DIR / "PHASE_64_4_BROKER_DEMO_EXECUTION_SAFETY_DESIGN.md",
        "Phase 64.4 broker demo execution safety design. See reports/phase64_4/PHASE64_4_FINAL_REPORT.md.\n",
    )

    # Data-flow architecture companion
    write_json(
        REPORTS_DIR / "architecture_data_flow.json",
        {
            "flow": architecture.get("data_flow"),
            "integration_points": architecture.get("integration_points"),
            "design_only": True,
        },
    )

    print(f"VERDICT={verdict}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_4_FINAL_REPORT.md'}", flush=True)
    return 0 if verdict == "BROKER_EXECUTION_DESIGN_VALIDATED" and unit_tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
