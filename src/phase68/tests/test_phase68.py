"""Phase 68 unit tests."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase65.consumption import build_consumption_registry
from phase67.exploratory import consumed_days
from phase68.adversarial import run_adversarial_tests
from phase68.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    DISPLACEMENT_ATR_MULT,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
)
from phase68.integrity import audit_integrity
from phase68.live_integrity import audit_live_evidence
from phase68.security import security_audit


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase68_displacement_response_live_integrity_v1")

    def test_posture(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_fixed_displacement(self):
        self.assertEqual(DISPLACEMENT_ATR_MULT, 1.5)


class TestLiveAndHoldout(unittest.TestCase):
    def test_holdout(self):
        cons = build_consumption_registry()
        self.assertFalse(set(consumed_days()) & set(cons["phase58_holdout_sealed"]))

    def test_live_backfill_split(self):
        live = audit_live_evidence()
        self.assertGreater(live["historical_init_backfill_m5"], 0)
        self.assertLess(live["newly_observed_live_closed_m5"], live["historical_init_backfill_m5"])
        self.assertTrue(live["integrity_verified"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        self.assertTrue(run_adversarial_tests()["suite_pass"])

    def test_security(self):
        self.assertTrue(security_audit()["pass"])

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
