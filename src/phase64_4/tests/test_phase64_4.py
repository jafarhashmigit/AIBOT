"""Unit tests for Phase 64.4 design & authorization gate."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_4.adversarial import run_adversarial_tests
from phase64_4.architecture_audit import audit_existing_architecture
from phase64_4.authorization_gate import (
    AuthorizationContext,
    attempt_unauthorized_submit,
    evaluate_authorization,
)
from phase64_4.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    DEMO_COLLECTION,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    RECIPE_ID,
)
from phase64_4.economics import audit_economics
from phase64_4.integrity import audit_integrity
from phase64_4.recovery_design import audit_recovery_design
from phase64_4.risk_spec import audit_risk_spec
from phase64_4.schemas import audit_schemas
from phase64_4.state_machine import audit_state_machine
from phase64_4.symbol_verification import audit_symbol_configuration
from phase64_4.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_4_broker_demo_execution_safety_design_v1")

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


class TestDesign(unittest.TestCase):
    def test_architecture(self):
        self.assertTrue(audit_existing_architecture()["pass"])

    def test_schemas(self):
        self.assertTrue(audit_schemas()["pass"])

    def test_state_machine(self):
        self.assertTrue(audit_state_machine()["pass"])

    def test_symbol(self):
        self.assertTrue(audit_symbol_configuration()["pass"])

    def test_risk(self):
        self.assertTrue(audit_risk_spec()["pass"])

    def test_economics(self):
        self.assertTrue(audit_economics()["pass"])

    def test_recovery(self):
        self.assertTrue(audit_recovery_design()["pass"])


class TestAuthorization(unittest.TestCase):
    def test_default_blocked(self):
        r = evaluate_authorization()
        self.assertFalse(r["submission_authorized"])
        self.assertFalse(r["broker_order_send_permitted"])
        self.assertEqual(r["state"], "BLOCKED_BY_AUTHORIZATION")

    def test_unauthorized_attempt(self):
        r = attempt_unauthorized_submit(AuthorizationContext())
        self.assertTrue(r["blocked"])
        self.assertFalse(r["reached_order_send"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])

    def test_verdict(self):
        bundle = {
            "architecture": audit_existing_architecture(),
            "schemas": audit_schemas(),
            "state_machine": audit_state_machine(),
            "symbol": audit_symbol_configuration(),
            "risk": audit_risk_spec(),
            "economics": audit_economics(),
            "recovery": audit_recovery_design(),
            "authorization": evaluate_authorization(),
            "adversarial": {"suite_pass": True},
            "integrity": audit_integrity(),
            "unit_tests": {"ok": True},
        }
        v, _ = choose_verdict(bundle)
        self.assertEqual(v, "BROKER_EXECUTION_DESIGN_VALIDATED")


if __name__ == "__main__":
    unittest.main()
