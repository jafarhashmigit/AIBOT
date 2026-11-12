"""Phase 64.6 runner — MT5 read-only readiness engineering (no order_send)."""

from __future__ import annotations

import json
import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase64_6.adversarial import run_adversarial_tests
from phase64_6.architecture_audit import audit_architecture
from phase64_6.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    UNAPPROVED,
)
from phase64_6.contract_integrity import audit_contract_integrity
from phase64_6.execution_gate import audit_execution_gate, threat_model
from phase64_6.integrity import audit_integrity
from phase64_6.progress import write_json, write_text
from phase64_6.readonly_adapter import FakeMt5Backend, ReadOnlyMetadataAdapter, assert_no_prohibited_in_adapter_source
from phase64_6.risk_policy import audit_risk_policy, propose_demo_risk_policy
from phase64_6.security_matrix import build_security_matrix
from phase64_6.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_6.tests.test_phase64_6")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_6.tests.test_phase64_6",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_5.tests.test_phase64_5",
        "phase64_4.tests.test_phase64_4",
        "phase64_3.tests.test_phase64_3",
    ]
    loader = unittest.TestLoader()
    all_ok = True
    details = []
    for name in suites:
        suite = loader.loadTestsFromName(name)
        result = unittest.TextTestRunner(verbosity=0).run(suite)
        details.append(
            {
                "suite": name,
                "tests_run": result.testsRun,
                "ok": result.wasSuccessful(),
                "failures": len(result.failures),
                "errors": len(result.errors),
            }
        )
        all_ok = all_ok and result.wasSuccessful()
    return {"ok": all_ok, "details": details}


def _genuine_evidence_count() -> dict[str, Any]:
    """Read Phase64.5 evidence counts if present — do not re-audit zero deals narratively beyond reporting."""
    path = REPORTS_DIR.parent / "phase64_5" / "evidence_counts.json"
    if not path.is_file():
        return {"genuine_broker_deals": 0, "source": "missing_phase64_5_counts", "note": "expected_zero_without_manual_trades"}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "genuine_broker_deals": int(data.get("genuine_broker_deals") or 0),
        "genuine_broker_orders": int(data.get("genuine_broker_orders") or 0),
        "genuine_balance_operations": int(data.get("genuine_balance_operations") or 0),
        "source": str(path),
        "note": "Zero trade deals expected without user manual trading; not re-audited as a work item",
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("architecture_audit", flush=True)
    architecture = audit_architecture()
    write_json(REPORTS_DIR / "architecture_audit.json", architecture)

    print("security_matrix", flush=True)
    security_matrix = build_security_matrix()
    write_json(REPORTS_DIR / "mt5_readonly_security_permission_matrix.json", security_matrix)

    print("readonly_adapter", flush=True)
    # Engineering validation uses FakeMt5Backend (no live credentials / no user trades required)
    adapter_bundle = ReadOnlyMetadataAdapter(backend=FakeMt5Backend()).fetch()
    adapter_src = assert_no_prohibited_in_adapter_source()
    adapter = {
        "engineering_pass": adapter_bundle.get("status") in ("OK", "OK_PARTIAL") and adapter_src["pass"],
        "bundle": adapter_bundle,
        "source_guard": adapter_src,
        "live_mt5_fetch": "NOT_RUN — no credentials; FakeMt5Backend used for reproducible engineering evidence",
        "note": "Live fetch available via LiveMt5Backend when terminal path supplied in a future authorized RO probe",
    }
    write_json(REPORTS_DIR / "readonly_metadata_adapter_result.json", adapter)

    print("contract_integrity", flush=True)
    contract = audit_contract_integrity(adapter_bundle.get("symbol") if adapter_bundle.get("status") != "BLOCKED" else None)
    write_json(REPORTS_DIR / "xauusdm_contract_metadata_completeness.json", contract)

    print("risk_policy", flush=True)
    # Use adapter account balance when present for proposed (still UNAPPROVED) numbers
    acct = (adapter_bundle.get("account") or {}) if adapter_bundle.get("status") != "BLOCKED" else {}
    risk_policy = audit_risk_policy()
    risk_proposal = propose_demo_risk_policy(
        account_balance=acct.get("balance"),
        account_currency=acct.get("currency"),
    )
    write_json(REPORTS_DIR / "demo_risk_policy_proposal_UNAPPROVED.json", risk_proposal)
    write_json(REPORTS_DIR / "risk_policy_validation.json", risk_policy)

    print("execution_gate", flush=True)
    execution_gate = audit_execution_gate()
    write_json(REPORTS_DIR / "execution_authorization_threat_model.json", threat_model())
    write_json(REPORTS_DIR / "execution_gate_validation.json", execution_gate)

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_audit.json", adversarial)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    unit_tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", unit_tests)

    print("regressions_64_5_64_4_64_3", flush=True)
    regressions = _run_regressions()
    write_json(REPORTS_DIR / "regression_results.json", regressions)

    genuine_evidence = _genuine_evidence_count()
    write_json(REPORTS_DIR / "genuine_evidence_snapshot.json", genuine_evidence)

    bundle = {
        "architecture": architecture,
        "security_matrix": security_matrix,
        "adapter": adapter,
        "contract": contract,
        "risk_policy": risk_policy,
        "execution_gate": execution_gate,
        "adversarial": adversarial,
        "integrity": integrity,
        "unit_tests": unit_tests,
        "genuine_evidence": genuine_evidence,
        "regressions": regressions,
    }
    write_json(REPORTS_DIR / "validation_results.json", bundle)
    verdict, reason, dims = choose_verdict(bundle)

    blockers = [
        "tick_size/tick_value not independently verified (UNKNOWN) — monetary risk calculators return INCOMPLETE",
        "trading_sessions incomplete / UNKNOWN via RO symbol_info alone",
        "positions_get / orders_get / history_* remain PROHIBITED — cannot native-reconcile open exposure",
        f"Risk policy approval_status={UNAPPROVED} — does not authorize execution",
        "Execution submission function unreachable; Automated Orders DISABLED",
        f"Genuine broker trade deals={genuine_evidence.get('genuine_broker_deals')} (expected without manual trades)",
    ]
    next_task = (
        "Separate security-review proposal for RO positions_get/orders_get/history_deals_get "
        "(not order_send), then live RO metadata probe with terminal path to fill UNKNOWN tick/account fields"
    )
    write_json(
        REPORTS_DIR / "remaining_blockers.json",
        {"blockers": blockers, "next_highest_impact_task": next_task},
    )

    changed = [
        "src/phase64_6/** (new)",
        "tests/phase64_6/** (new)",
        "reports/phase64_6/** (new)",
        "docs/agent/PHASE_64_6_MT5_READONLY_READINESS.md (new)",
    ]

    report = "\n".join(
        [
            "# Phase 64.6 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**Broker Execution Ready:** `{BROKER_EXECUTION_READY}`",
            f"**Reason:** {reason}",
            f"**Generated:** `{now}`",
            "",
            "## Dimensions (not conflated)",
            f"- Engineering readiness: `{dims.get('engineering_readiness')}`",
            f"- Broker metadata completeness: `{dims.get('broker_metadata_completeness')}`",
            f"- Risk policy approval status: `{dims.get('risk_policy_approval_status')}`",
            f"- Execution authorization status: `{dims.get('execution_authorization_status')}`",
            f"- Genuine broker evidence count (deals): `{dims.get('genuine_broker_evidence_count')}`",
            "",
            "## Workstream results",
            f"- Architecture audit pass: `{architecture.get('pass')}`",
            f"- Security matrix pass: `{security_matrix.get('pass')}` | allowlist modified: `{security_matrix.get('allowlist_modified')}`",
            f"- Blocked readiness APIs (pending separate review): `{security_matrix.get('minimum_ro_capabilities_blocked_pending_review')}`",
            f"- RO adapter engineering pass: `{adapter.get('engineering_pass')}` | live fetch: `{adapter.get('live_mt5_fetch')}`",
            f"- Contract integrity pass: `{contract.get('pass')}` | complete: `{(contract.get('metadata_completeness') or {}).get('complete')}`",
            f"- Risk policy: `{UNAPPROVED}` authorizes_execution=`False`",
            f"- Execution gate pass: `{execution_gate.get('pass')}` | submission_reachable=`False`",
            "",
            "## Tests",
            f"- Unit OK=`{unit_tests.get('ok')}` run=`{unit_tests.get('tests_run')}`",
            f"- Adversarial: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
            f"- Regressions 64.5/64.4/64.3 OK=`{regressions.get('ok')}`",
            f"- Integrity checks_pass=`{integrity.get('checks_pass')}` | Phase0–64.5 modified=`{integrity.get('phase0_64_5_source_modified')}`",
            "",
            "## Changed files",
            *[f"- `{c}`" for c in changed],
            "",
            "## Remaining blockers",
            *[f"- {b}" for b in blockers],
            "",
            f"**Next highest-impact task:** {next_task}",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_6.run_phase64_6",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_6_FINAL_REPORT.md", report)
    write_text(
        DOCS_DIR / "PHASE_64_6_MT5_READONLY_READINESS.md",
        "Phase 64.6 MT5 read-only readiness. See reports/phase64_6/PHASE64_6_FINAL_REPORT.md.\n",
    )

    print(f"VERDICT={verdict}", flush=True)
    print(f"dims={dims}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_6_FINAL_REPORT.md'}", flush=True)
    ok = verdict == "MT5_READ_ONLY_READINESS_VALIDATED" and unit_tests.get("ok") and regressions.get("ok")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
