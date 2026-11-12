"""Phase 64.5 runner — broker evidence ingestion & reconciliation (READ-ONLY)."""

from __future__ import annotations

import shutil
import time
import unittest
from datetime import datetime, timezone
from typing import Any

from phase64_5.adversarial import run_adversarial_tests
from phase64_5.architecture_audit import audit_architecture
from phase64_5.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    CHAMPION_STATUS,
    DEMO_COLLECTION,
    DOCS_DIR,
    JOURNAL_ROOT,
    LIVE_TRADING,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    SIMULATED_LABEL,
)
from phase64_5.economics import build_cost_ledger
from phase64_5.export_discovery import discover_all
from phase64_5.formats import audit_formats, supported_format_specification
from phase64_5.import_pipeline import import_genuine_exports, write_simulated_fixtures
from phase64_5.integrity import audit_integrity
from phase64_5.journal import BrokerEvidenceJournal
from phase64_5.linkage import link_journal_events
from phase64_5.progress import write_json, write_text
from phase64_5.reconciliation import reconcile, reconcile_twice
from phase64_5.recovery import run_recovery_suite
from phase64_5.verdict import choose_verdict
from phase64_5.constants import FIXTURES_DIR


def _run_tests() -> dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("phase64_5.tests.test_phase64_5")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "command": "python -m unittest phase64_5.tests.test_phase64_5",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "ok": result.wasSuccessful(),
    }


def main() -> int:
    t0 = time.perf_counter()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("architecture_audit", flush=True)
    architecture = audit_architecture()
    write_json(REPORTS_DIR / "architecture_audit.json", architecture)

    print("formats", flush=True)
    formats = audit_formats()
    write_json(REPORTS_DIR / "supported_export_format_specification.json", supported_format_specification())
    write_json(REPORTS_DIR / "formats_validation.json", formats)

    print("discovery", flush=True)
    discovery = discover_all()
    write_json(REPORTS_DIR / "export_discovery.json", discovery)

    print("genuine_import", flush=True)
    # Fresh genuine journal each run under data root (append-only within run; recreate dir for clean phase report)
    if JOURNAL_ROOT.exists():
        shutil.rmtree(JOURNAL_ROOT)
    genuine_journal = BrokerEvidenceJournal(JOURNAL_ROOT / "genuine", allow_synthetic=False, store_label="GENUINE")
    genuine_import = import_genuine_exports(genuine_journal)
    write_json(REPORTS_DIR / "genuine_import_result.json", genuine_import)
    write_json(REPORTS_DIR / "raw_evidence_integrity.json", genuine_journal.integrity_report())

    print("fixture_parser_validation", flush=True)
    fx = write_simulated_fixtures(FIXTURES_DIR)
    sim_journal = BrokerEvidenceJournal(JOURNAL_ROOT / "simulated", allow_synthetic=True, store_label=SIMULATED_LABEL)
    from phase64_5.import_pipeline import import_csv_file
    from pathlib import Path

    sim_import = import_csv_file(
        sim_journal, Path(fx["deals"]), synthetic=True, evidence_label=SIMULATED_LABEL
    )
    write_json(REPORTS_DIR / "simulated_fixture_import.json", sim_import)

    print("linkage_reconciliation", flush=True)
    genuine_events = genuine_journal.all_events()
    sim_events = sim_journal.all_events()
    genuine_link = link_journal_events(genuine_events, aibot_intents=[])
    sim_link = link_journal_events(
        sim_events, aibot_intents=[{"intent_id": "INTENT_SIM_1", "decision_id": "DEC_SIM"}]
    )
    genuine_recon = reconcile(events=genuine_events, aibot_intents=[], linkage=genuine_link)
    sim_recon = reconcile(
        events=sim_events,
        aibot_intents=[{"intent_id": "INTENT_SIM_1", "decision_id": "DEC_SIM"}],
        linkage=sim_link,
    )
    recon_idem = reconcile_twice(
        sim_events, aibot_intents=[{"intent_id": "INTENT_SIM_1", "decision_id": "DEC_SIM"}]
    )
    write_json(
        REPORTS_DIR / "linkage_results.json",
        {"genuine": genuine_link, "simulated_fixture": sim_link},
    )
    write_json(
        REPORTS_DIR / "reconciliation_results.json",
        {"genuine": genuine_recon, "simulated_fixture": sim_recon, "idempotency": recon_idem},
    )

    print("economics", flush=True)
    genuine_econ = build_cost_ledger(genuine_events)
    sim_econ = build_cost_ledger(sim_events)
    write_json(
        REPORTS_DIR / "cost_ledger.json",
        {"genuine": genuine_econ, "simulated_fixture": sim_econ},
    )

    print("adversarial", flush=True)
    adversarial = run_adversarial_tests()
    write_json(REPORTS_DIR / "adversarial_audit.json", adversarial)

    print("recovery", flush=True)
    recovery = run_recovery_suite()
    write_json(REPORTS_DIR / "journal_recovery_tests.json", recovery)

    print("integrity", flush=True)
    integrity = audit_integrity()
    write_json(REPORTS_DIR / "phase_integrity_audit.json", integrity)

    print("unit_tests", flush=True)
    unit_tests = _run_tests()
    write_json(REPORTS_DIR / "test_results.json", unit_tests)

    counts = genuine_import.get("counts") or {}
    evidence_counts = {
        "source_files_discovered": discovery.get("n_source_files_discovered"),
        "genuine_files_accepted_for_parse": discovery.get("n_accepted_for_parse"),
        "genuine_files_rejected": discovery.get("n_rejected"),
        "genuine_broker_orders": counts.get("genuine_broker_orders", 0),
        "genuine_broker_deals": counts.get("genuine_broker_deals", 0),
        "genuine_broker_fills": counts.get("genuine_broker_fills", 0),
        "genuine_balance_operations": counts.get("genuine_balance_operations", 0),
        "duplicate_records_on_genuine_import": (genuine_import.get("totals") or {}).get("duplicates", 0),
        "quarantined_records": counts.get("quarantined", 0),
        "verified_aibot_decision_to_deal_links": (genuine_link.get("counts") or {}).get("VERIFIED_LINK", 0),
        "unverified_candidates": (genuine_link.get("counts") or {}).get("UNVERIFIED_CANDIDATE", 0),
        "unmatched_broker_records": (genuine_link.get("counts") or {}).get("UNMATCHED_BROKER_RECORD", 0),
        "reconciliation_conflicts": sum(
            1 for f in (genuine_recon.get("findings") or []) if "CONFLICT" in str(f.get("status"))
        ),
        "complete_cost_records_genuine": genuine_econ.get("n_complete_fragments", 0),
        "incomplete_cost_records_genuine": genuine_econ.get("n_incomplete", 0),
        "simulated_fixture_deals_ingested": sim_import.get("stats", {}).get("deals", 0),
        "note": "Simulated fixture counts are NOT genuine broker integration evidence",
    }
    write_json(REPORTS_DIR / "evidence_counts.json", evidence_counts)

    bundle = {
        "architecture": architecture,
        "formats": formats,
        "discovery": discovery,
        "genuine_import": genuine_import,
        "adversarial": adversarial,
        "recovery": recovery,
        "integrity": integrity,
        "unit_tests": unit_tests,
        "reconciliation": genuine_recon,
    }
    write_json(REPORTS_DIR / "validation_results.json", bundle)
    verdict, reason = choose_verdict(bundle)

    defects = {
        "high": [
            "Genuine XAUUSDm trade deals = 0 — only balance-only XLSX history present (or awaiting CSV).",
            "Timezone provenance UNKNOWN for all imported timestamps.",
            "history_deals_get still PROHIBITED; no native MT5 history API.",
        ],
        "medium": [
            "CSV exports still preferred for deal-rich evidence; XLSX Trade History is supported but empty of trades.",
            "Verified linkage requires explicit aibot_intent tags in broker comments — none on genuine records.",
            "Cost ledger incomplete without commission/swap/fee on deals.",
        ],
        "low": [
            "phase0_64_4_source_modified is policy-asserted (Phase64.5 adds new package only).",
            "Account login observed in XLSX label is not a credential; still avoid storing secrets.",
        ],
    }
    write_json(REPORTS_DIR / "remaining_defects.json", defects)

    changed = [
        "src/phase64_5/** (new)",
        "tests/phase64_5/** (new)",
        "reports/phase64_5/** (new)",
        "docs/agent/PHASE_64_5_BROKER_EVIDENCE_RECONCILIATION.md (new)",
        "src/data/phase64_5/** (new journal/fixtures)",
    ]

    report = "\n".join(
        [
            "# Phase 64.5 — Final Report",
            "",
            f"**Recipe:** `{RECIPE_ID}`",
            f"**Verdict:** `{verdict}`",
            f"**Champion:** `{CHAMPION_STATUS}` | **Production:** `{PRODUCTION_FINAL_ACTION}` | **Live:** `{LIVE_TRADING}`",
            f"**Automated Orders:** `{AUTOMATED_ORDERS}` | **Demo Collection:** `{DEMO_COLLECTION}`",
            f"**Broker Execution Ready:** `{BROKER_EXECUTION_READY}`",
            f"**Reason:** {reason}",
            f"**Generated:** `{now}`",
            "",
            "## Safety posture",
            "- READ-ONLY evidence foundation; no `order_send`; no order submit/modify/cancel.",
            f"- Submission path: none | Allowlist expanded: `{integrity.get('allowlist_expanded')}`",
            "",
            "## Architecture",
            f"- Pass: `{architecture.get('pass')}` | Duplicate lifecycle avoided: `{architecture.get('duplicate_lifecycle_avoided')}`",
            f"- Reuses Phase62–64.4 patterns; new journal owned by Phase64.5.",
            "",
            "## Export discovery & formats",
            f"- Source files discovered: `{evidence_counts['source_files_discovered']}`",
            f"- Accepted for parse: `{evidence_counts['genuine_files_accepted_for_parse']}` | Rejected: `{evidence_counts['genuine_files_rejected']}`",
            f"- Formats pass: `{formats.get('pass')}` — see `supported_export_format_specification.json`",
            "",
            "## Genuine import (actual evidence)",
            f"- Status: `{genuine_import.get('status')}`",
            f"- Genuine broker orders: `{evidence_counts['genuine_broker_orders']}`",
            f"- Genuine broker deals: `{evidence_counts['genuine_broker_deals']}`",
            f"- Genuine broker fills: `{evidence_counts['genuine_broker_fills']}`",
            f"- Balance-only records: `{evidence_counts['genuine_balance_operations']}`",
            f"- Duplicates: `{evidence_counts['duplicate_records_on_genuine_import']}` | Quarantined: `{evidence_counts['quarantined_records']}`",
            f"- Fabricated evidence: `{genuine_import.get('fabricated_evidence')}`",
            "",
            "## Simulated fixture validation (NOT genuine)",
            f"- Label: `{SIMULATED_LABEL}`",
            f"- Fixture deals ingested: `{evidence_counts['simulated_fixture_deals_ingested']}`",
            f"- Verified links (fixture): `{(sim_link.get('counts') or {}).get('VERIFIED_LINK')}`",
            "",
            "## Linkage (genuine)",
            f"- VERIFIED_LINK: `{evidence_counts['verified_aibot_decision_to_deal_links']}`",
            f"- UNVERIFIED_CANDIDATE: `{evidence_counts['unverified_candidates']}`",
            f"- UNMATCHED_BROKER_RECORD: `{evidence_counts['unmatched_broker_records']}`",
            "- Rule: no inference from timestamp/direction/volume/price alone.",
            "",
            "## Reconciliation",
            f"- Genuine findings: `{genuine_recon.get('n_findings')}` | unresolved: `{genuine_recon.get('n_unresolved')}`",
            f"- Idempotent repeated recon (fixture): `{recon_idem.get('pass')}`",
            f"- Silently reconciled unknowns: `{genuine_recon.get('silently_reconciled_unknowns')}`",
            "",
            "## Cost completeness",
            f"- Genuine complete fragments: `{evidence_counts['complete_cost_records_genuine']}`",
            f"- Genuine incomplete: `{evidence_counts['incomplete_cost_records_genuine']}`",
            f"- Aggregate: `{genuine_econ.get('aggregate_net_execution_economics')}`",
            "",
            "## Tests",
            f"- Unit OK=`{unit_tests.get('ok')}` run=`{unit_tests.get('tests_run')}`",
            f"- Adversarial: `{adversarial.get('suite_pass')}` (`{adversarial.get('n_pass')}`/`{adversarial.get('n_cases')}`)",
            f"- Recovery: `{recovery.get('suite_pass')}` (`{recovery.get('n_pass')}`/`{recovery.get('n_cases')}`)",
            "",
            "## Immutability",
            f"- Phase0–64.4 source modified: `{integrity.get('phase0_64_4_source_modified')}`",
            f"- Prior reports present: `{integrity.get('prior_reports_present')}`",
            f"- Stores merged: `{integrity.get('stores_merged')}` | Phase58 sealed: `{integrity.get('phase58_holdout_sealed')}`",
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
            "## Next recommended action",
            "1. After real XAUUSDm demo trades exist, export History→Deals CSV into `src/data/phase63/exports/genuine` or `src/data/phase64_5/exports/genuine`.",
            "2. Re-run `python -m phase64_5.run_phase64_5` and confirm genuine deal counts > 0.",
            "3. Keep Automated Orders DISABLED; do not expand MT5 allowlist; do not start Phase65.",
            "4. Optional: tag EA comments with `aibot_intent:<intent_id>` only after a future authorized demo-execution review.",
            "",
            "## Commands",
            "```powershell",
            "$env:PYTHONPATH='src'",
            ".\\.venv\\Scripts\\python.exe -m phase64_5.run_phase64_5",
            ".\\.venv\\Scripts\\python.exe -m unittest phase64_5.tests.test_phase64_5 phase64_4.tests.test_phase64_4",
            "```",
            "",
            f"Runtime s: `{time.perf_counter() - t0}`",
            "",
        ]
    )
    write_text(REPORTS_DIR / "PHASE64_5_FINAL_REPORT.md", report)
    write_text(
        DOCS_DIR / "PHASE_64_5_BROKER_EVIDENCE_RECONCILIATION.md",
        "Phase 64.5 broker evidence ingestion & reconciliation. See reports/phase64_5/PHASE64_5_FINAL_REPORT.md.\n",
    )

    print(f"VERDICT={verdict}", flush=True)
    print(f"report={REPORTS_DIR / 'PHASE64_5_FINAL_REPORT.md'}", flush=True)
    return 0 if verdict == "BROKER_EVIDENCE_RECONCILIATION_VALIDATED" and unit_tests.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
