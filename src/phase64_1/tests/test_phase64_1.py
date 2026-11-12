"""Phase 64.1 tests — canonical identity + intent integration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase57.fixtures import clean_bundle
from phase64_1.adversarial import run_adversarial_tests
from phase64_1.constants import EXPECTED_NULL_POLICY, RECIPE_ID
from phase64_1.crash_suite import run_crash_matrix
from phase64_1.engine import make_canonical_engine
from phase64_1.identity import identity_contract, make_canonical_decision_id
from phase64_1.integrity import audit_integrity, phase58_holdout
from phase64_1.market_snapshot import MarketSnapshotStore, build_snapshot_from_observation
from phase64_1.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_null_policy(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_1_canonical_decision_execution_intent_integration_v1")

    def test_holdout(self):
        self.assertEqual(len(phase58_holdout()), 10)

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)


class TestIdentitySnapshot(unittest.TestCase):
    def test_deterministic_id(self):
        a = make_canonical_decision_id(
            domain="AGENT_SHADOW",
            symbol="XAUUSDm",
            timeframe="M5",
            bar_timestamp_utc="t",
            snapshot_hash="h",
            policy_version="p",
        )
        b = make_canonical_decision_id(
            domain="AGENT_SHADOW",
            symbol="XAUUSDm",
            timeframe="M5",
            bar_timestamp_utc="t",
            snapshot_hash="h",
            policy_version="p",
        )
        self.assertEqual(a, b)
        self.assertFalse(identity_contract()["historical_ids_rewritten"])

    def test_snapshot_immutable_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            store = MarketSnapshotStore(Path(td))
            body = build_snapshot_from_observation(
                {
                    "accepted": True,
                    "symbol": "XAUUSDm",
                    "timeframe": "M5",
                    "bar_timestamp_utc": "t1",
                    "observation_id": "o1",
                    "market_state_id": "m1",
                    "bid": 10.0,
                    "ask": 10.1,
                    "data_quality_status": "OK",
                }
            )
            s1 = store.commit(body)
            s2 = store.commit(body)
            self.assertEqual(s1["snapshot_id"], s2["snapshot_id"])
            ok, _ = store.verify(s1["snapshot_id"])
            self.assertTrue(ok)


class TestIntegration(unittest.TestCase):
    def test_end_to_end_buy_path(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            day, m5, h1, by = clean_bundle(day="2099-10-01", move_after_entry=-4.0)
            eng = make_canonical_engine(
                work=work,
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
                account_profile={"broker": "Exness", "environment": "DEMO", "symbol": "XAUUSDm", "digits": 3},
            )
            out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            stages = [t["stage"] for t in out["trace"]]
            self.assertIn("MARKET_SNAPSHOT", stages)
            self.assertIn("EXECUTION_INTENT", stages)
            self.assertEqual(out["decision"]["decision_id_scheme"], "phase64_1_canonical_v1")
            self.assertTrue(out["intent"]["executable"] or out["decision"]["action"] == "WAIT")
            if out.get("position"):
                self.assertEqual(out["position"]["intent_id"], out["intent"]["intent_id"])
                self.assertEqual(out["position"]["decision_id"], out["decision"]["decision_id"])
            # idempotent second pass
            out2 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertTrue(out2.get("skipped"))
            self.assertEqual(len(eng.intent_journal.all_intents()), 1)

    def test_wait_non_executable(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            day, m5, h1, by = clean_bundle(day="2099-10-02")
            eng = make_canonical_engine(work=work, policy=NullPolicy())
            out = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(out["intent"]["intent_status"], "NO_TRADE_WAIT")
            self.assertFalse(out["intent"]["executable"])
            self.assertIsNone(out.get("position"))


class TestCrashAdversarial(unittest.TestCase):
    def test_crash_matrix(self):
        suite = run_crash_matrix()
        self.assertTrue(suite["suite_pass"], suite)

    def test_adversarial(self):
        a = run_adversarial_tests()
        self.assertTrue(a["pass"], a)


class TestIntegrityVerdict(unittest.TestCase):
    def test_integrity(self):
        a = audit_integrity()
        self.assertFalse(a["phase0_63_source_modified"])
        self.assertFalse(a["allowlist_expanded"])
        self.assertTrue(a["checks_pass"])

    def test_verdict_ready_when_green(self):
        v, _ = choose_verdict(
            integration_ok=True,
            crash_ok=True,
            adversarial_ok=True,
            integrity_ok=True,
            tests_ok=True,
            null_ok=True,
            end_to_end_paper=True,
        )
        self.assertEqual(v, "CANONICAL_DECISION_INTENT_INTEGRATION_READY")


if __name__ == "__main__":
    unittest.main()
