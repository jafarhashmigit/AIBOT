"""Phase 64 unit tests — readiness audit; no broker execution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64.adversarial import run_adversarial_tests
from phase64.constants import EXPECTED_NULL_POLICY, RECIPE_ID
from phase64.crash_recovery import run_crash_recovery_suite
from phase64.evidence_integrity import audit_cost_fields, slippage
from phase64.execution_intent import (
    ExecutionIntentJournal,
    create_execution_intent,
    mark_cancelled,
    mark_expired,
)
from phase64.integrity import audit_integrity, phase58_holdout
from phase64.lifecycle_audit import audit_lifecycle
from phase64.linkage import independent_decision_count, link_deal_fill, link_order
from phase64.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_null_policy(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_recipe_id(self):
        self.assertEqual(RECIPE_ID, "phase64_demo_decision_execution_readiness_audit_v1")

    def test_holdout_sealed(self):
        self.assertEqual(len(phase58_holdout()), 10)

    def test_order_send_prohibited(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        # Phase64.8 approved history_deals_get RO; order_send remains prohibited.
        from phase12.mt5_allowlist import PERMITTED_MT5_API

        self.assertIn("history_deals_get", PERMITTED_MT5_API)


class TestLifecycle(unittest.TestCase):
    def test_stage_matrix(self):
        m = audit_lifecycle()
        self.assertIn("FUTURE_BROKER_ORDER", m["summary"]["missing"])
        self.assertEqual(m["stages"]["DECISION"]["status"], "EXISTS")
        self.assertEqual(m["stages"]["EXECUTION_INTENT"]["status"], "PARTIAL")
        self.assertEqual(m["stages"]["FUTURE_BROKER_ORDER"].get("broker_test_status"), "NOT_TESTED")
        self.assertTrue(m["safety"]["order_send_prohibited"])


class TestIntentAndLinkage(unittest.TestCase):
    def test_unique_decision_and_intent_ids(self):
        with tempfile.TemporaryDirectory() as td:
            j = ExecutionIntentJournal(Path(td))
            ids = set()
            intent_ids = set()
            for i in range(3):
                d = {
                    "decision_id": f"dec{i}",
                    "timestamp_utc": "2026-11-11T12:00:00Z",
                    "action": "WAIT",
                    "proposed_action": "WAIT",
                    "instrument": "XAUUSDm",
                    "observation_id": f"o{i}",
                    "market_state_id": f"XAUUSDm:M5:{i}",
                    "execution_assumptions": {},
                }
                r = create_execution_intent(
                    j,
                    decision=d,
                    risk={"allowed": True, "final_action": "WAIT", "reasons": []},
                    account_profile={"symbol": "XAUUSDm", "fixture": True},
                )
                ids.add(d["decision_id"])
                intent_ids.add(r["intent_id"])
            self.assertEqual(len(ids), 3)
            self.assertEqual(len(intent_ids), 3)

    def test_partial_fills_one_decision(self):
        with tempfile.TemporaryDirectory() as td:
            j = ExecutionIntentJournal(Path(td))
            d = {
                "decision_id": "dec_pf",
                "timestamp_utc": "2026-11-11T12:00:00Z",
                "action": "BUY",
                "proposed_action": "BUY",
                "instrument": "XAUUSDm",
                "observation_id": "o",
                "market_state_id": "XAUUSDm:M5:t",
                "execution_assumptions": {"bid_ref": 1.0, "ask_ref": 1.1},
            }
            created = create_execution_intent(
                j,
                decision=d,
                risk={"allowed": True, "final_action": "BUY", "reasons": []},
                account_profile={"symbol": "XAUUSDm", "fixture": True},
            )
            link_order(j, intent_id=created["intent_id"], decision_id=d["decision_id"], order_id="O")
            link_deal_fill(
                j,
                intent_id=created["intent_id"],
                decision_id=d["decision_id"],
                deal_id="D1",
                order_id="O",
                actual_fill_price=1.11,
                requested_price=1.1,
                volume=0.01,
                fill_kind="PARTIAL",
            )
            link_deal_fill(
                j,
                intent_id=created["intent_id"],
                decision_id=d["decision_id"],
                deal_id="D2",
                order_id="O",
                actual_fill_price=1.12,
                requested_price=1.1,
                volume=0.01,
                fill_kind="FULL",
            )
            c = independent_decision_count(j)
            self.assertEqual(c["n_independent_decisions"], 1)
            self.assertEqual(c["n_fill_rows"], 2)

    def test_cancelled_expired(self):
        with tempfile.TemporaryDirectory() as td:
            j = ExecutionIntentJournal(Path(td))
            d = {
                "decision_id": "dec_ce",
                "timestamp_utc": "2026-11-11T12:00:00Z",
                "action": "BUY",
                "proposed_action": "BUY",
                "instrument": "XAUUSDm",
                "observation_id": "o",
                "market_state_id": "m",
                "execution_assumptions": {"ask_ref": 1.1, "bid_ref": 1.0},
            }
            created = create_execution_intent(
                j,
                decision=d,
                risk={"allowed": True, "final_action": "BUY", "reasons": []},
                account_profile={"symbol": "XAUUSDm", "fixture": True},
            )
            mark_cancelled(j, intent_id=created["intent_id"], decision_id=d["decision_id"])
            self.assertEqual(j.get_intent(created["intent_id"])["intent_status"], "CANCELLED")
            created2 = create_execution_intent(
                j,
                decision={**d, "decision_id": "dec_ex"},
                risk={"allowed": True, "final_action": "BUY", "reasons": []},
                account_profile={"symbol": "XAUUSDm", "fixture": True},
            )
            mark_expired(j, intent_id=created2["intent_id"], decision_id="dec_ex")
            self.assertEqual(j.get_intent(created2["intent_id"])["intent_status"], "EXPIRED")

    def test_block_genuine_fabricated_flag(self):
        with tempfile.TemporaryDirectory() as td:
            j = ExecutionIntentJournal(Path(td))
            with self.assertRaises(ValueError):
                link_order(j, intent_id="i", decision_id="d", order_id="o", genuine_broker=True)


class TestEvidenceIntegrity(unittest.TestCase):
    def test_unknown_not_zero(self):
        c = audit_cost_fields({"commission": 0, "commission_source": "MISSING", "fee": None, "swap": None})
        self.assertIn("commission_zero_without_evidence", c["issues"])
        self.assertEqual(c["normalized"]["commission"], "UNKNOWN")

    def test_slippage_unknown_without_prices(self):
        s = slippage(side="BUY", requested_price=None, actual_fill_price=1.0)
        self.assertEqual(s["slippage"], "UNKNOWN")

    def test_slippage_direction_buy(self):
        s = slippage(side="BUY", requested_price=100.0, actual_fill_price=100.5)
        self.assertEqual(s["direction"], "ADVERSE")


class TestCrashAndAdversarial(unittest.TestCase):
    def test_crash_suite(self):
        suite = run_crash_recovery_suite()
        self.assertTrue(suite["suite_pass"], suite)

    def test_adversarial(self):
        a = run_adversarial_tests()
        self.assertTrue(a["pass"], a)


class TestIntegrityVerdict(unittest.TestCase):
    def test_integrity(self):
        a = audit_integrity()
        self.assertFalse(a["phase0_63_source_modified"])
        self.assertFalse(a["allowlist_expanded"])
        self.assertFalse(a["stores_merged"])
        self.assertFalse(a["broker_execution_activated"])
        self.assertTrue(a["checks_pass"])

    def test_verdict_not_broker_ready(self):
        lifecycle = audit_lifecycle()
        crash = {"suite_pass": True}
        v, reason = choose_verdict(
            lifecycle=lifecycle,
            crash_suite=crash,
            traceability={"genuine_broker_orders_linked": 0},
            integrity={"checks_pass": True},
            tests_ok=True,
            null_ok=True,
            genuine_broker_fills=0,
        )
        self.assertEqual(v, "DEMO_DECISION_EXECUTION_READINESS_PARTIAL")
        self.assertIn("not broker-execution-ready", reason)


if __name__ == "__main__":
    unittest.main()
