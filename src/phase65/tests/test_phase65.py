"""Unit tests for Phase 65 research gates (no order_send)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_13.constants import CLOSE_ONLY, OPEN
from phase64_13.schedule import state_at_utc
from phase65.adversarial import run_adversarial_tests
from phase65.constants import (
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
from phase65.consumption import build_consumption_registry
from phase65.cost_stress import cost_taxonomy
from phase65.integrity import audit_integrity
from phase65.registry import build_and_freeze_registry


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase65_independent_edge_discovery_v1")

    def test_champion_wait(self):
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


class TestRegistryAndHoldout(unittest.TestCase):
    def test_consumption_and_prereg(self):
        c = build_consumption_registry()
        self.assertTrue(c["sufficient_unconsumed_for_discovery"])
        self.assertFalse(c["phase58_holdout_opened"])
        r = build_and_freeze_registry(
            discovery_days=c["phase65_discovery"],
            validation_days=c["phase65_validation"],
        )
        self.assertTrue(r["preregistered"])
        self.assertEqual(r["n"], 3)

    def test_session_states_distinct(self):
        co = state_at_utc(datetime(2026, 11, 10, 23, 1, 0, tzinfo=timezone.utc))
        op = state_at_utc(datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(co["state"], CLOSE_ONLY)
        self.assertEqual(op["state"], OPEN)

    def test_cost_unknown_not_zero(self):
        t = cost_taxonomy()
        self.assertTrue(t["commission"]["never_zero"])
        self.assertTrue(t["swap"]["never_zero"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
