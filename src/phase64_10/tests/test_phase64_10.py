"""Unit tests for Phase 64.10."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_10.adversarial import run_adversarial_tests
from phase64_10.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    RECIPE_ID,
    UNAPPROVED,
)
from phase64_10.economics_matrix import build_economics_bundle
from phase64_10.integrity import audit_integrity
from phase64_10.risk_policy import build_demo_risk_policy
from phase64_10.scorecard import build_readiness_scorecard
from phase64_10.stress import build_stress_framework


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_10_broker_economics_risk_execution_readiness_v1")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")

    def test_submission_disabled(self):
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_posture(self):
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(PHASE65, "NOT_STARTED")


class TestCore(unittest.TestCase):
    def test_economics_bundle(self):
        b = build_economics_bundle()
        self.assertEqual(b["commission"]["actual_commission_observed"], "UNKNOWN")
        self.assertEqual(b["margin"]["MARGIN_MODEL"], "INCOMPLETE")
        self.assertEqual(b["sessions"]["programmatic_status"], "UNKNOWN")
        self.assertEqual(b["swap"]["status_for_execution"], "UNKNOWN_FOR_EXECUTION")
        self.assertFalse(b["cost_model"]["deterministic_execution_cost_complete"])

    def test_risk_policy_unapproved(self):
        p = build_demo_risk_policy()
        self.assertEqual(p["approval_status"], UNAPPROVED)
        self.assertFalse(p["authorizes_execution"])

    def test_scorecard_blocks(self):
        b = build_economics_bundle()
        p = build_demo_risk_policy()
        sc = build_readiness_scorecard(
            commission=b["commission"],
            margin=b["margin"],
            sessions=b["sessions"],
            swap=b["swap"],
            cost_model=b["cost_model"],
            risk_policy=p,
        )
        self.assertFalse(sc["execution_ready"])
        self.assertGreater(sc["n_blocking"], 0)
        # UNKNOWN must not be PASS for commission/sessions
        statuses = {r["dependency"]: r["status"] for r in sc["rows"]}
        self.assertNotEqual(statuses["Commission"], "PASS")
        self.assertNotEqual(statuses["Sessions"], "PASS")

    def test_stress(self):
        s = build_stress_framework(expected_edge_usd=5.0)
        self.assertTrue(s["never_manufacture_edge"])
        self.assertGreater(s["scenarios"]["combined_stress"]["usd"], 0)


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
