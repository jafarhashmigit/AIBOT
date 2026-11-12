"""Unit tests for Phase 67."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase65.consumption import build_consumption_registry
from phase67.adversarial import run_adversarial_tests
from phase67.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
)
from phase67.exploratory import consumed_days
from phase67.hypotheses import future_hypothesis_candidates
from phase67.integrity import audit_integrity
from phase67.security import security_audit
from phase67.tick_api_audit import audit_tick_api_approval


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase67_exness_evidence_exploratory_v1")

    def test_champion(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)


class TestTickAndHoldout(unittest.TestCase):
    def test_ticks_not_approved(self):
        a = audit_tick_api_approval()
        self.assertFalse(a["any_tick_api_approved"])
        self.assertFalse(a["phase67_uses_ticks"])

    def test_no_holdout_in_consumed(self):
        cons = build_consumption_registry()
        self.assertFalse(set(consumed_days()) & set(cons["phase58_holdout_sealed"]))
        self.assertFalse(cons["phase58_holdout_opened"])

    def test_hypotheses_max_five(self):
        h = future_hypothesis_candidates()
        self.assertLessEqual(h["n"], 5)
        self.assertFalse(h["confirmatory_tests_run"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])

    def test_security(self):
        self.assertTrue(security_audit()["pass"])


if __name__ == "__main__":
    unittest.main()
