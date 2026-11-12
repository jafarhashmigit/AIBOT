"""Unit tests for Phase 64.8."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PERMITTED_MT5_API, PHASE64_8_APPROVED_READ_ONLY, PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_5.journal import BrokerEvidenceJournal
from phase64_8.adversarial import run_adversarial_tests
from phase64_8.approval_matrix import build_approval_matrix
from phase64_8.collector import collect_fake
from phase64_8.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_READY,
    DEMO_COLLECTION,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    ORDER_SEND,
    RECIPE_ID,
    UNAPPROVED,
)
from phase64_8.evidence_backend import FakeEvidenceBackend
from phase64_8.integrity import audit_integrity
from phase64_8.reconcile import reconcile_lifecycle, state_machine_spec
from phase64_8.security import audit_security_invariants


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_8_readonly_broker_evidence_reconciliation_v1")

    def test_order_send_prohibited(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")

    def test_ro_apis_approved(self):
        for api in PHASE64_8_APPROVED_READ_ONLY:
            self.assertIn(api, PERMITTED_MT5_API)
            self.assertNotIn(api, PROHIBITED_MT5_API)

    def test_totals_still_prohibited(self):
        self.assertIn("positions_total", PROHIBITED_MT5_API)
        self.assertIn("orders_total", PROHIBITED_MT5_API)

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_posture(self):
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(DEMO_COLLECTION, "READ_ONLY")
        self.assertEqual(BROKER_COLLECTION, "READ_ONLY")
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(UNAPPROVED, "UNAPPROVED")
        self.assertIs(BROKER_EXECUTION_READY, False)


class TestCore(unittest.TestCase):
    def test_approval_matrix(self):
        m = build_approval_matrix()
        self.assertTrue(m["pass"], m)
        self.assertEqual(
            set(m["summary"]["APPROVED_READ_ONLY"]),
            {"positions_get", "orders_get", "history_deals_get", "history_orders_get"},
        )

    def test_empty_collection_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backend = FakeEvidenceBackend()
            r1 = collect_fake(root, backend)
            r2 = collect_fake(root, backend)
            self.assertEqual(r1["status"], "COLLECTED")
            self.assertEqual(r2["status"], "COLLECTED")
            self.assertEqual(r1["n_positions"], 0)
            self.assertEqual(r1["n_open_orders"], 0)
            self.assertGreaterEqual(r2["ingest_stats"]["DUPLICATE_SUPPRESSED"], 1)
            j = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
            self.assertTrue(j.integrity_report()["index_matches"])

    def test_recon_state_machine(self):
        spec = state_machine_spec()
        self.assertIn("RECONCILED", spec["states"])
        self.assertIn("ORPHAN_BROKER_EVIDENCE", spec["exception_states"])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            collect_fake(root, FakeEvidenceBackend())
            j = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
            recon = reconcile_lifecycle(events=j.all_events())
            self.assertTrue(recon["empty_flags"]["positions_empty"])
            self.assertFalse(recon["fill_reconciliation_validated"])

    def test_security(self):
        self.assertTrue(audit_security_invariants()["pass"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
