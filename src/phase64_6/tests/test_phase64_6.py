"""Unit tests for Phase 64.6."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_6.adversarial import run_adversarial_tests
from phase64_6.architecture_audit import audit_architecture
from phase64_6.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    DEMO_COLLECTION,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    RECIPE_ID,
    UNAPPROVED,
)
from phase64_6.contract_integrity import audit_contract_integrity
from phase64_6.execution_gate import audit_execution_gate
from phase64_6.integrity import audit_integrity
from phase64_6.readonly_adapter import FakeMt5Backend, ReadOnlyMetadataAdapter
from phase64_6.risk_policy import audit_risk_policy
from phase64_6.security_matrix import build_security_matrix
from phase64_6.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_6_broker_execution_readiness_mt5_readonly_security_v1")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)

    def test_allowlist_phase64_8_ro_expansion(self):
        """Phase64.6 left allowlist unchanged; Phase64.8 approved four RO APIs. Mutation stays prohibited."""
        self.assertIn("symbol_info", PERMITTED_MT5_API)
        self.assertIn("positions_get", PERMITTED_MT5_API)
        self.assertIn("history_deals_get", PERMITTED_MT5_API)
        self.assertIn("order_send", PROHIBITED_MT5_API)

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_posture(self):
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(DEMO_COLLECTION, "READ_ONLY")
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertIs(BROKER_EXECUTION_READY, False)


class TestEngineering(unittest.TestCase):
    def test_architecture(self):
        self.assertTrue(audit_architecture()["pass"])

    def test_security_matrix(self):
        self.assertTrue(build_security_matrix()["pass"])

    def test_adapter_happy_partial(self):
        r = ReadOnlyMetadataAdapter(backend=FakeMt5Backend()).fetch()
        self.assertIn(r["status"], ("OK", "OK_PARTIAL"))
        self.assertFalse(r["execution_authorized"])
        self.assertFalse(r["critical_metadata_complete"])  # tick_value unknown in fake

    def test_contract(self):
        self.assertTrue(audit_contract_integrity()["pass"])

    def test_risk_unapproved(self):
        r = audit_risk_policy()
        self.assertTrue(r["pass"])
        self.assertEqual(r["with_demo_balance_still_unapproved"]["approval_status"], UNAPPROVED)

    def test_execution_gate(self):
        self.assertTrue(audit_execution_gate()["pass"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])

    def test_verdict_dimensions(self):
        bundle = {
            "architecture": audit_architecture(),
            "security_matrix": build_security_matrix(),
            "adapter": {"engineering_pass": True},
            "contract": audit_contract_integrity(),
            "risk_policy": audit_risk_policy(),
            "execution_gate": audit_execution_gate(),
            "adversarial": {"suite_pass": True},
            "integrity": audit_integrity(),
            "unit_tests": {"ok": True},
            "genuine_evidence": {"genuine_broker_deals": 0},
        }
        v, _, dims = choose_verdict(bundle)
        self.assertEqual(v, "MT5_READ_ONLY_READINESS_VALIDATED")
        self.assertEqual(dims["risk_policy_approval_status"], UNAPPROVED)
        self.assertEqual(dims["execution_authorization_status"], "NOT_AUTHORIZED")
        self.assertEqual(dims["genuine_broker_evidence_count"], 0)
        self.assertEqual(dims["broker_metadata_completeness"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
