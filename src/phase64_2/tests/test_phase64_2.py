"""Phase 64.2 unit tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase57.fixtures import clean_bundle
from phase64_2.adversarial import run_adversarial_tests
from phase64_2.constants import EXPECTED_NULL_POLICY, RECIPE_ID, STATUS_PAPER_FINALIZED, STATUS_WAIT_FINALIZED
from phase64_2.crash_suite import run_crash_matrix
from phase64_2.engine import make_hardened_engine
from phase64_2.identity_guard import IdentityConflictError, register_or_reuse_bar_decision
from phase64_2.integrity import audit_integrity, phase58_holdout
from phase64_2.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_2_intent_identity_wait_durability_v1")

    def test_holdout(self):
        self.assertEqual(len(phase58_holdout()), 10)

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)


class TestIntentWaitIdentity(unittest.TestCase):
    def test_buy_finalizes_intent(self):
        with tempfile.TemporaryDirectory() as td:
            day, m5, h1, by = clean_bundle(day="2099-11-10", move_after_entry=-4.0)
            eng = make_hardened_engine(
                work=Path(td),
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
            )
            out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(out["intent"]["intent_status"], STATUS_PAPER_FINALIZED)
            self.assertTrue(out["intent_audit"]["consistent"])

    def test_wait_durable_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            day, m5, h1, by = clean_bundle(day="2099-11-11")
            eng = make_hardened_engine(work=Path(td), policy=EngineeringTestPolicy(["WAIT"]))
            out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(out["intent"]["intent_status"], STATUS_WAIT_FINALIZED)
            eid = out["wait_durable"]["experience_id"]
            n1 = eng.shadow.n
            out2 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertTrue(out2.get("skipped"))
            self.assertEqual(eng.shadow.n, n1)
            self.assertTrue(eid)

    def test_bar_identity_conflict(self):
        m: dict = {}
        register_or_reuse_bar_decision(
            m, day="d", idx=0, canonical_decision_id="a", snapshot_hash="h1", proposed_action="WAIT"
        )
        with self.assertRaises(IdentityConflictError):
            register_or_reuse_bar_decision(
                m, day="d", idx=0, canonical_decision_id="a", snapshot_hash="h2", proposed_action="WAIT"
            )


class TestSuites(unittest.TestCase):
    def test_crash(self):
        s = run_crash_matrix()
        self.assertTrue(s["suite_pass"], s)

    def test_adversarial(self):
        a = run_adversarial_tests()
        self.assertTrue(a["pass"], a)


class TestIntegrity(unittest.TestCase):
    def test_integrity(self):
        a = audit_integrity()
        self.assertFalse(a["phase0_64_1_source_modified"])
        self.assertTrue(a["checks_pass"])

    def test_verdict(self):
        v, _ = choose_verdict(
            crash_ok=True,
            adversarial_ok=True,
            integrity_ok=True,
            tests_ok=True,
            null_ok=True,
            consistency_ok=True,
        )
        self.assertEqual(v, "INTENT_IDENTITY_WAIT_DURABILITY_HARDENED")


if __name__ == "__main__":
    unittest.main()
