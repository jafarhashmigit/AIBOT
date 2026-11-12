"""Unit tests for Phase 64.9."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_9.adapter import BrokerExecutionAdapter
from phase64_9.adversarial import run_adversarial_tests
from phase64_9.authorization import evaluate_authorization
from phase64_9.constants import (
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
from phase64_9.fake_broker import FakeBrokerBackend, run_fake_broker_suite
from phase64_9.integrity import audit_integrity
from phase64_9.intent_fsm import ExecutionIntentStore
from phase64_9.path_trace import build_path_trace
from phase64_9.preflight import PreflightContext, run_preflight, symbol_spec_hash
from phase64_9.recovery import run_recovery_suite
from phase64_9.risk_calc import run_risk_calc_tests
from phase64_9.security_review import build_order_send_security_review
from phase64_9.constants import (
    ACTIVE_SYMBOL,
    EXPECTED_CURRENCY,
    EXPECTED_DEMO_LOGIN,
    EXPECTED_SERVER,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_DIGITS,
    VERIFIED_TICK_SIZE,
    VERIFIED_TICK_VALUE,
)


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_9_order_submission_security_execution_preflight_v1")

    def test_order_send_prohibited(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")

    def test_submission_hard_disabled(self):
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_posture(self):
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(UNAPPROVED, "UNAPPROVED")
        self.assertEqual(PHASE65, "NOT_STARTED")


class TestCore(unittest.TestCase):
    def test_security_review(self):
        self.assertTrue(build_order_send_security_review()["pass"])

    def test_path_trace(self):
        self.assertTrue(build_path_trace()["pass"])

    def test_risk_calc(self):
        self.assertTrue(run_risk_calc_tests()["suite_pass"])

    def test_preflight_reject_unapproved_risk(self):
        s = symbol_spec_hash(
            tick_size=VERIFIED_TICK_SIZE,
            tick_value=VERIFIED_TICK_VALUE,
            contract_size=VERIFIED_CONTRACT_SIZE,
            digits=VERIFIED_DIGITS,
            volume_min=0.01,
            volume_step=0.01,
        )
        ctx = PreflightContext(
            account_fingerprint="fp",
            expected_fingerprint="fp",
            server=EXPECTED_SERVER,
            currency=EXPECTED_CURRENCY,
            login=EXPECTED_DEMO_LOGIN,
            symbol=ACTIVE_SYMBOL,
            symbol_spec_hash=s,
            expected_symbol_spec_hash=s,
            bid=2649.5,
            ask=2650.0,
            tick_age_sec=1.0,
            trading_session_known=True,
            in_trading_session=True,
            direction="BUY",
            volume=0.01,
            price=2650.0,
            sl=2649.0,
            tp=2652.0,
            filling_mode_bitmask=7,
            requested_filling=1,
            commission=-0.06,
            risk_policy_status=UNAPPROVED,
            decision_id="d",
            decision_action="BUY",
            execution_intent_id="i",
        )
        r = run_preflight(ctx)
        self.assertEqual(r["status"], "PREFLIGHT_REJECTED")
        self.assertIn("risk_policy_unapproved", r["reasons"])

    def test_adapter_blocked(self):
        r = BrokerExecutionAdapter().submit({"intent_id": "x"})
        self.assertEqual(r["status"], "BLOCKED")
        self.assertFalse(r["reached_order_send"])

    def test_fake_broker(self):
        self.assertTrue(run_fake_broker_suite()["suite_pass"])

    def test_intent_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionIntentStore(Path(td))
            a = store.create_intent(decision_id="d1", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
            b = store.create_intent(decision_id="d1", direction="BUY", volume=0.01, symbol=ACTIVE_SYMBOL)
            self.assertEqual(a["status"], "CREATED")
            self.assertEqual(b["status"], "DUPLICATE_REJECTED")

    def test_auth_false(self):
        self.assertFalse(evaluate_authorization()["authorized"])

    def test_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(run_recovery_suite(Path(td))["suite_pass"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
