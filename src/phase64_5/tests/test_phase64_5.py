"""Unit tests for Phase 64.5."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_5.adversarial import run_adversarial_tests
from phase64_5.architecture_audit import audit_architecture
from phase64_5.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    DEMO_COLLECTION,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    RECIPE_ID,
    SIMULATED_LABEL,
)
from phase64_5.export_discovery import discover_all
from phase64_5.formats import audit_formats
from phase64_5.import_pipeline import import_csv_file, import_genuine_exports, write_simulated_fixtures
from phase64_5.integrity import audit_integrity
from phase64_5.journal import BrokerEvidenceJournal
from phase64_5.recovery import run_recovery_suite
from phase64_5.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_5_broker_evidence_ingestion_reconciliation_v1")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_holdout(self):
        integ = audit_integrity()
        self.assertTrue(integ["phase58_holdout_sealed"])
        self.assertFalse(integ["phase58_used"])

    def test_posture(self):
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(DEMO_COLLECTION, "READ_ONLY")
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertIs(BROKER_EXECUTION_READY, False)


class TestCore(unittest.TestCase):
    def test_architecture(self):
        self.assertTrue(audit_architecture()["pass"])

    def test_formats(self):
        self.assertTrue(audit_formats()["pass"])

    def test_discovery(self):
        d = discover_all()
        self.assertGreaterEqual(d["n_source_files_discovered"], 0)

    def test_simulated_parser(self):
        with tempfile.TemporaryDirectory() as td:
            fx = write_simulated_fixtures(Path(td) / "fx")
            j = BrokerEvidenceJournal(Path(td) / "j", allow_synthetic=True, store_label=SIMULATED_LABEL)
            r = import_csv_file(j, Path(fx["deals"]), synthetic=True, evidence_label=SIMULATED_LABEL)
            self.assertEqual(r["status"], "IMPORTED")
            self.assertGreater(r["stats"]["deals"], 0)

    def test_genuine_import_honest_zero(self):
        with tempfile.TemporaryDirectory() as td:
            j = BrokerEvidenceJournal(Path(td) / "genuine", allow_synthetic=False, store_label="GENUINE")
            # Uses discovery roots (may include phase63 xlsx)
            res = import_genuine_exports(j)
            self.assertFalse(res["fabricated_evidence"])
            self.assertTrue(res["read_only"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_recovery(self):
        s = run_recovery_suite()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])

    def test_verdict(self):
        bundle = {
            "architecture": audit_architecture(),
            "formats": audit_formats(),
            "discovery": discover_all(),
            "genuine_import": {
                "fabricated_evidence": False,
                "read_only": True,
                "counts": {"genuine_broker_deals": 0},
            },
            "adversarial": {"suite_pass": True},
            "recovery": {"suite_pass": True},
            "integrity": audit_integrity(),
            "unit_tests": {"ok": True},
            "reconciliation": {"silently_reconciled_unknowns": False},
        }
        v, _ = choose_verdict(bundle)
        self.assertEqual(v, "BROKER_EVIDENCE_RECONCILIATION_VALIDATED")


if __name__ == "__main__":
    unittest.main()
