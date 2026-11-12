"""Phase 64.8 runner — RO broker evidence reconciliation (no order_send / no Phase65)."""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase64_8.adversarial import run_adversarial_tests
from phase64_8.approval_matrix import build_approval_matrix
from phase64_8.collector import collect_live
from phase64_8.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_READY,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    LIVE_JOURNAL_ROOT,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    UNAPPROVED,
)
from phase64_8.integrity import audit_integrity
from phase64_8.progress import write_json, write_text
from phase64_8.reconcile import reconcile_lifecycle, state_machine_spec
from phase64_8.security import audit_security_invariants
from phase64_8.verdict import choose_verdict
from phase64_5.journal import BrokerEvidenceJournal


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_8.tests.test_phase64_8")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_8.tests.test_phase64_8",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def _run_regressions() -> dict[str, Any]:
    """Run each suite in an isolated subprocess so live MT5 imports cannot pollute Phase12 tests."""
    import subprocess
    import sys

    suites = [
        "phase64_7.tests.test_phase64_7",
        "phase64_6.tests.test_phase64_6",
        "phase64_5.tests.test_phase64_5",
        "phase64_4.tests.test_phase64_4",
        "phase12.tests.test_phase12b",
        "phase62.tests.test_phase62",
        "phase63.tests.test_phase63",
        "phase64.tests.test_phase64",
    ]
    details = []
    ok = True
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(__import__("pathlib").Path(__file__).resolve().parents[1])
    for name in suites:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", name, "-q"],
            capture_output=True,
            text=True,
            env=env,
        )
        suite_ok = proc.returncode == 0
        details.append(
            {
                "suite": name,
                "returncode": proc.returncode,
                "ok": suite_ok,
                "stderr_tail": (proc.stderr or "")[-500:],
            }
        )
        ok = ok and suite_ok
    return {"ok": ok, "details": details}


def _journal_schema() -> dict[str, Any]:
    return {
        "schema_version": "phase64_8_broker_evidence_journal_v1",
        "store": "BROKER_EVIDENCE",
        "append_only": True,
        "record_kinds": [
            "BROKER_ACCOUNT",
            "BROKER_POSITION",
            "BROKER_ORDER",
            "BROKER_DEAL",
            "BROKER_BALANCE_OPERATION",
        ],
        "identity": {
            "execution_identity_keys": ["position:{ticket}", "order:{ticket}", "hist_order:{ticket}", "deal:{ticket}"],
            "observation_keys": ["obs_account:{fingerprint}:{retrieved_at}", "obs_*:{UNKNOWN}"],
            "idempotency": "stable_key + body_hash; duplicate suppressed; conflict quarantined",
        },
        "forbidden_keys": sorted(
            ["password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"]
        ),
        "never_merge_with": ["HISTORICAL_HYPOTHETICAL", "PAPER"],
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_JOURNAL_ROOT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("approval_matrix", flush=True)
    approval = build_approval_matrix()
    write_json(REPORTS_DIR / "api_approval_matrix.json", approval)
    write_json(REPORTS_DIR / "phase12_allowlist_diff.json", approval.get("allowlist_diff") or {})

    print("live_ro_collection", flush=True)
    live1 = collect_live(LIVE_JOURNAL_ROOT)
    live2 = collect_live(LIVE_JOURNAL_ROOT)  # idempotent repeat
    write_json(REPORTS_DIR / "live_collection_cycle1.json", live1)
    write_json(REPORTS_DIR / "live_collection_cycle2_idempotent.json", live2)

    journal = BrokerEvidenceJournal(LIVE_JOURNAL_ROOT, allow_synthetic=False, store_label="GENUINE")
    events = journal.all_events()
    recon = reconcile_lifecycle(events=events)
    write_json(REPORTS_DIR / "live_reconciliation.json", recon)
    write_json(REPORTS_DIR / "journal_integrity.json", journal.integrity_report())
    write_json(REPORTS_DIR / "broker_evidence_journal_schema.json", _journal_schema())
    write_json(REPORTS_DIR / "reconciliation_state_machine.json", state_machine_spec())
    write_json(
        REPORTS_DIR / "evidence_identity_idempotency_spec.json",
        {
            "rules": [
                "Prefer broker ticket identifiers for execution identity",
                "Account snapshots use observation-level keys",
                "Repeated polling must not create duplicate canonical evidence",
                "Never match solely by timestamp, price, or volume",
                "Conflicts quarantine; never auto-resolve by proximity",
            ],
            "wal_recovery": True,
            "stable_key_classes": ["EXECUTION_IDENTITY", "OBSERVATION"],
        },
    )

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_audit.json", adversarial)

    print("security", flush=True)
    security = audit_security_invariants()
    write_json(REPORTS_DIR / "security_invariants.json", security)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", tests)

    print("regressions", flush=True)
    regressions = _run_regressions()
    write_json(REPORTS_DIR / "regression_results.json", regressions)

    verdict = choose_verdict(
        approval=approval,
        live=live1,
        recon=recon,
        adversarial=adversarial,
        security=security,
        integrity=integrity,
        tests_ok=bool(tests.get("ok")),
        regressions_ok=bool(regressions.get("ok")),
    )
    write_json(REPORTS_DIR / "verdict.json", verdict)

    swap_conflict = {
        "phase63_user_reported_swap_long": -488.7,
        "phase64_7_live_swap_long": -644.8,
        "overwrite": False,
        "provenance_preserved": True,
        "note": "Phase64.8 does not resolve or overwrite this conflict",
    }
    write_json(REPORTS_DIR / "swap_long_conflict_preserved.json", swap_conflict)

    remaining = [
        "Genuine trade fill reconciliation not validated (0 trade deals; balance op only if present)",
        "Trading sessions remain UNKNOWN",
        "Commission schedule remains UNKNOWN",
        "Usable initial/maintenance margin remain UNKNOWN",
        "swap_long conflict preserved (Phase63 -488.7 vs Phase64.7 -644.8)",
        "Risk policy remains UNAPPROVED",
        "Execution authorization NOT_AUTHORIZED; order_send PROHIBITED",
        "No Phase65 trading authorization",
    ]
    write_json(REPORTS_DIR / "remaining_blockers.json", {"blockers": remaining})

    dims = verdict["dimensions"]
    report = "\n".join(
        [
            "# Phase 64.8 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict['verdict']}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Broker Collection:** `{BROKER_COLLECTION}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**Broker Execution Ready:** `{BROKER_EXECUTION_READY}` | **order_send:** `{ORDER_SEND}`",
            f"**Risk Policy:** `{UNAPPROVED}`",
            f"**Reason:** {verdict['reason']}",
            f"**Generated:** `{now}`",
            "",
            "## Dimensions (not conflated)",
            *[f"- {k}: `{v}`" for k, v in dims.items()],
            "",
            "## API approval",
            f"- Pass: `{approval.get('pass')}`",
            f"- APPROVED_READ_ONLY: `{approval['summary']['APPROVED_READ_ONLY']}`",
            f"- REJECTED: `{approval['summary']['REJECTED']}`",
            f"- Allowlist added: `{approval['allowlist_diff']['added_to_permitted']}`",
            f"- Mutation still prohibited: `{approval['allowlist_diff']['still_prohibited_mutation']}`",
            "",
            "## Live RO collection",
            f"- Cycle1 status: `{live1.get('status')}`",
            f"- Cycle2 status: `{live2.get('status')}` (idempotent repeat)",
            f"- Positions: `{live1.get('n_positions')}` | Open orders: `{live1.get('n_open_orders')}`",
            f"- Trade deals: `{live1.get('n_trade_deals')}` | Balance ops: `{live1.get('n_balance_operations')}`",
            f"- Cycle2 duplicates suppressed: `{(live2.get('ingest_stats') or {}).get('DUPLICATE_SUPPRESSED')}`",
            f"- Order send invoked: `{live1.get('order_send_invoked')}`",
            f"- Fill reconciliation validated: `{recon.get('fill_reconciliation_validated')}`",
            "",
            "## Journal / recon",
            f"- Journal index_matches: `{(journal.integrity_report() or {}).get('index_matches')}`",
            f"- Recon findings: `{recon.get('n_findings')}`",
            f"- States seen: `{recon.get('states_seen')}`",
            "",
            "## Tests",
            f"- Unit OK=`{tests.get('ok')}` run=`{tests.get('tests_run')}`",
            f"- Adversarial: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
            f"- Regressions OK=`{regressions.get('ok')}`",
            f"- Integrity: `{integrity.get('checks_pass')}` | Security: `{security.get('pass')}`",
            "",
            "## Invariants",
            *[f"- {k}: `{v}`" for k, v in verdict["invariants"].items()],
            "",
            "## Remaining blockers",
            *[f"- {b}" for b in remaining],
            "",
            "**Next highest-impact task:** Design (still non-executing) risk-policy proposal + "
            "paper↔broker linkage rehearsal using this RO evidence layer — do **not** start Phase65 "
            "trading authorization or enable `order_send`.",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_8.run_phase64_8",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_8_FINAL_REPORT.md", report)
    write_text(
        DOCS_DIR / "PHASE_64_8_READONLY_BROKER_EVIDENCE_RECONCILIATION.md",
        report,
    )

    print(verdict["verdict"], flush=True)
    return 0 if verdict["verdict"] != "BROKER_RO_RECONCILIATION_BLOCKED" and tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
