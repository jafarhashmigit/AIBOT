"""Phase 64.7 runner — live RO probe + API security review (no orders, allowlist unchanged)."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase64_7.adversarial import run_adversarial_tests
from phase64_7.api_security_review import build_api_security_review
from phase64_7.constants import (
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
from phase64_7.contract_recalc import recalculate_from_probe
from phase64_7.execution_recon_design import audit_recon_design, execution_reconciliation_design
from phase64_7.integrity import audit_integrity
from phase64_7.live_probe import run_live_probe
from phase64_7.metadata_reconciliation import reconcile_metadata
from phase64_7.progress import write_json, write_text
from phase64_7.verdict import choose_verdict


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_7.tests.test_phase64_7")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_7.tests.test_phase64_7",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    suites = [
        "phase64_6.tests.test_phase64_6",
        "phase64_5.tests.test_phase64_5",
        "phase64_4.tests.test_phase64_4",
    ]
    loader = unittest.TestLoader()
    details = []
    ok = True
    for name in suites:
        result = unittest.TextTestRunner(verbosity=0).run(loader.loadTestsFromName(name))
        details.append({"suite": name, "tests_run": result.testsRun, "ok": result.wasSuccessful()})
        ok = ok and result.wasSuccessful()
    return {"ok": ok, "details": details}


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("live_probe", flush=True)
    probe = run_live_probe()
    write_json(REPORTS_DIR / "live_ro_probe_raw.json", probe.get("raw") or probe)
    write_json(REPORTS_DIR / "live_ro_probe_sanitized.json", probe.get("sanitized") or {"status": probe.get("status")})

    print("metadata_reconciliation", flush=True)
    reconciliation = reconcile_metadata(probe)
    write_json(REPORTS_DIR / "xauusdm_metadata_reconciliation.json", reconciliation)
    write_json(
        REPORTS_DIR / "account_metadata_completeness.json",
        {
            "account_metadata_complete": reconciliation.get("account_metadata_complete"),
            "xauusdm_critical_metadata_complete": reconciliation.get("xauusdm_critical_metadata_complete"),
            "remaining_unknown_or_unobserved": reconciliation.get("remaining_unknown_or_unobserved"),
            "conflicts": reconciliation.get("conflicts"),
        },
    )

    print("api_security_review", flush=True)
    api_security = build_api_security_review()
    write_json(REPORTS_DIR / "mt5_api_security_permission_matrix.json", api_security)
    write_json(
        REPORTS_DIR / "minimal_allowlist_change_proposal.json",
        api_security.get("minimal_allowlist_change_proposal"),
    )

    print("execution_recon_design", flush=True)
    recon_design = audit_recon_design()
    write_json(REPORTS_DIR / "execution_reconciliation_design.json", execution_reconciliation_design())

    print("contract_recalc", flush=True)
    contract = recalculate_from_probe(probe)
    write_json(REPORTS_DIR / "contract_calculation_evidence.json", contract)

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_audit.json", adversarial)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    unit_tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", unit_tests)

    print("regressions", flush=True)
    regressions = _run_regressions()
    write_json(REPORTS_DIR / "regression_results.json", regressions)

    bundle = {
        "probe": probe,
        "reconciliation": reconciliation,
        "api_security": api_security,
        "contract": contract,
        "adversarial": adversarial,
        "integrity": integrity,
        "unit_tests": unit_tests,
        "regressions": regressions,
        "recon_design": recon_design,
    }
    write_json(REPORTS_DIR / "validation_results.json", bundle)
    verdict, reason, dims = choose_verdict(bundle)

    blockers = []
    if probe.get("status") != "LIVE_PROBE_OK":
        blockers.append(f"Live probe blocked: {probe.get('block_reason') or probe.get('status')}")
    for c in reconciliation.get("conflicts") or []:
        blockers.append(
            f"Metadata conflict on {c['field']}: existing={c['existing_value']} observed={c['observed_value']}"
        )
    for u in reconciliation.get("remaining_unknown_or_unobserved") or []:
        blockers.append(f"Still unknown/unobserved: {u}")
    blockers.extend(
        [
            "positions_get/orders_get/history_* remain PROHIBITED — realtime order recon blocked",
            f"Risk policy remains {UNAPPROVED}",
            "Execution authorization NOT_AUTHORIZED; no order_send",
        ]
    )
    next_task = (
        "Approve (or reject) minimal RO allowlist additions for positions_get/orders_get/history_deals_get "
        "under documented controls; then wire recon into BrokerEvidenceJournal — still no order_send"
    )
    write_json(REPORTS_DIR / "remaining_blockers.json", {"blockers": blockers, "next_highest_impact_task": next_task})

    changed = [
        "src/phase64_7/** (new)",
        "tests/phase64_7/** (new)",
        "reports/phase64_7/** (new)",
        "docs/agent/PHASE_64_7_LIVE_MT5_READONLY_PROBE.md (new)",
    ]

    report = "\n".join(
        [
            "# Phase 64.7 — Final Report",
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
            *[f"- {k}: `{v}`" for k, v in dims.items()],
            "",
            "## Live probe",
            f"- Status: `{probe.get('status')}`",
            f"- Evidence type: `{(probe.get('raw') or probe).get('evidence_type')}`",
            f"- Fixture used: `{False if probe.get('status') == 'LIVE_PROBE_OK' else 'N/A'}`",
            f"- Order send invoked: `False`",
            "",
            "## Metadata reconciliation",
            f"- Account complete: `{reconciliation.get('account_metadata_complete')}`",
            f"- XAUUSDm critical complete: `{reconciliation.get('xauusdm_critical_metadata_complete')}`",
            f"- Conflicts: `{reconciliation.get('n_conflicts')}` (both sides preserved; no overwrite)",
            f"- Newly observed (was UNKNOWN): `{len(reconciliation.get('previously_unknown_now_observed') or [])}`",
            "",
            "## API security / allowlist",
            f"- Review pass: `{api_security.get('pass')}` | Allowlist changed: `False`",
            f"- Proposal status: `{(api_security.get('minimal_allowlist_change_proposal') or {}).get('status')}`",
            "",
            "## Contract recalculation",
            f"- Completeness: `{contract.get('contract_calculation_completeness')}`",
            f"- Risk policy approval: `{contract.get('risk_policy_approval_status')}`",
            "",
            "## Tests",
            f"- Unit OK=`{unit_tests.get('ok')}` run=`{unit_tests.get('tests_run')}`",
            f"- Adversarial: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
            f"- Regressions 64.6/64.5/64.4 OK=`{regressions.get('ok')}`",
            f"- Integrity: `{integrity.get('checks_pass')}` | Phase0–64.6 modified=`{integrity.get('phase0_64_6_source_modified')}`",
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
            ".\\.venv\\Scripts\\python.exe -m phase64_7.run_phase64_7",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_7_FINAL_REPORT.md", report)
    write_text(
        DOCS_DIR / "PHASE_64_7_LIVE_MT5_READONLY_PROBE.md",
        "Phase 64.7 live MT5 RO probe. See reports/phase64_7/PHASE64_7_FINAL_REPORT.md.\n",
    )

    print(f"VERDICT={verdict}", flush=True)
    print(f"dims={dims}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_7_FINAL_REPORT.md'}", flush=True)
    return 0 if verdict == "LIVE_MT5_METADATA_VERIFIED" and unit_tests.get("ok") and regressions.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
