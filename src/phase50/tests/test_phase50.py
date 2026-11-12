"""Phase50 mandatory tests."""

from __future__ import annotations

import unittest

from phase50.availability import assert_no_leakage, experience_available_at, outcome_known_before
from phase50.controls import make_randomizer
from phase50.experience_store import ExperienceStore, new_experience
from phase50.learner import ShrinkageLearner
from phase50.policies import decide
from phase50.schemas import experience_schema, validate_experience


class TestSchemaAndStores(unittest.TestCase):
    def test_schema_hash(self) -> None:
        s = experience_schema()
        self.assertIn("schema_sha256", s)
        self.assertTrue(s["merge_forbidden"])

    def test_separate_stores(self) -> None:
        h = ExperienceStore("HISTORICAL_HYPOTHETICAL")
        s = ExperienceStore("AGENT_SHADOW")
        h.clear()
        s.clear()
        rec = new_experience(
            source="HISTORICAL_HYPOTHETICAL",
            decision_timestamp_utc="2025-07-03 10:00:00",
            market_state_id="m",
            action="BUY",
            decision_context={"bucket_id": "x"},
            actual_costed_outcome_net_r=0.1,
            outcome_horizon_bars=12,
            outcome_timestamp_utc="2025-07-03 11:00:00",
            regime_context={},
        )
        self.assertEqual(validate_experience(rec), [])
        h.append(rec)
        with self.assertRaises(ValueError):
            s.append(rec)  # wrong source into shadow
        self.assertEqual(h.n, 1)
        self.assertEqual(s.n, 0)


class TestCausality(unittest.TestCase):
    def test_future_invisible(self) -> None:
        self.assertFalse(outcome_known_before("2025-07-03 12:00:00", "2025-07-03 11:00:00"))
        recs = [
            {
                "experience_id": "1",
                "outcome_timestamp_utc": "2025-07-03 12:00:00",
                "action": "BUY",
                "actual_costed_outcome_net_r": 1.0,
                "decision_context": {},
            }
        ]
        vis = experience_available_at(recs, "2025-07-03 11:00:00")
        self.assertEqual(vis, [])
        leak = assert_no_leakage(recs, "2025-07-03 11:00:00")
        self.assertFalse(leak["ok"])


class TestLearnerPolicy(unittest.TestCase):
    def test_wait_default(self) -> None:
        d = decide(policy_id="POLICY_0", q=None, experience_count=0)
        self.assertEqual(d["action"], "WAIT")

    def test_shrinkage_determinism(self) -> None:
        learner = ShrinkageLearner()
        exps = [
            new_experience(
                source="HISTORICAL_HYPOTHETICAL",
                decision_timestamp_utc="2025-07-03 10:00:00",
                market_state_id="m",
                action="BUY",
                decision_context={"bucket_id": "spr:low|ov:1|va:0"},
                actual_costed_outcome_net_r=1.0,
                outcome_horizon_bars=12,
                outcome_timestamp_utc="2025-07-03 11:00:00",
                regime_context={},
            )
            for _ in range(30)
        ]
        # need SELL too for structure
        for _ in range(30):
            exps.append(
                new_experience(
                    source="HISTORICAL_HYPOTHETICAL",
                    decision_timestamp_utc="2025-07-03 10:00:00",
                    market_state_id="m",
                    action="SELL",
                    decision_context={"bucket_id": "spr:low|ov:1|va:0"},
                    actual_costed_outcome_net_r=-0.5,
                    outcome_horizon_bars=12,
                    outcome_timestamp_utc="2025-07-03 11:00:00",
                    regime_context={},
                )
            )
        e1 = learner.fit_estimates(exps)
        e2 = learner.fit_estimates(exps)
        self.assertEqual(e1["global_mean"], e2["global_mean"])
        q = learner.q_values(e1, {"bucket_id": "spr:low|ov:1|va:0"})
        d = decide(policy_id="POLICY_1", q=q, experience_count=60)
        self.assertIn(d["action"], ("BUY", "SELL", "WAIT"))


class TestControls(unittest.TestCase):
    def test_randomizer_preserves_counts(self) -> None:
        batch = [
            {
                "action": "BUY",
                "actual_costed_outcome_net_r": float(i),
                "outcome_timestamp_utc": "t",
                "decision_context": {},
                "experience_id": str(i),
                "source": "HISTORICAL_HYPOTHETICAL",
                "decision_timestamp_utc": "d",
                "market_state_id": "m",
                "outcome_horizon_bars": 12,
                "regime_context": {},
                "feature_representation_version": "v",
                "policy_version": "p",
                "creation_timestamp_utc": "c",
                "experience_schema_version": "e",
                "learner_version": "l",
                "expected_value": None,
                "confidence": None,
            }
            for i in range(10)
        ]
        out = make_randomizer(1)(batch)
        self.assertEqual(len(out), 10)
        self.assertAlmostEqual(sum(r["actual_costed_outcome_net_r"] for r in out), sum(range(10)))


if __name__ == "__main__":
    unittest.main()
