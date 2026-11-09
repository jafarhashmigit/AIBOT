"""Fifteen required Phase 9 tests. No holdout. No package changes."""

from __future__ import annotations

import inspect
import unittest

import numpy as np

from phase6.information_boundary import InformationBoundaryError
from phase6.risk_gate import RiskGate
from phase8.experience_schema import outcome_end_for
from phase9.audit import snapshot_protected
from phase9.constants import (
    MIN_EXPERIENCES_PER_SIDE,
    PHASE9_LEARNER_FEATURE_ALLOWLIST,
    PROTECTED_HASHES,
    RIDGE_ALPHA,
)
from phase9.decision_policy import experience_rule
from phase9.learner import ExperienceRidge, assert_allowlist, features_from_pair, vector
from phase9.online_learning import OnlineLoop
from phase9.replay import replay
from phase9.tests.factories import eval_row, pair, series, stamps


def _feat(ts: str = "2026-06-19 10:00:00"):
    return features_from_pair(pair(ts))


class Phase9Tests(unittest.TestCase):
    def test_01_learner_schema_validation(self):
        feat = _feat()
        self.assertEqual(tuple(feat.keys()), PHASE9_LEARNER_FEATURE_ALLOWLIST)
        self.assertEqual(len(vector(feat)), len(PHASE9_LEARNER_FEATURE_ALLOWLIST))

    def test_02_decision_time_feature_allowlist(self):
        feat = dict(_feat())
        feat["session_flag"] = 1.0
        with self.assertRaises(InformationBoundaryError):
            assert_allowlist(feat)

    def test_03_outcome_field_rejection(self):
        feat = dict(_feat())
        feat["realized_R"] = 1.0
        with self.assertRaises(InformationBoundaryError):
            assert_allowlist(feat)
        feat = dict(_feat())
        feat["actual_net_r"] = 0.2
        with self.assertRaises(InformationBoundaryError):
            assert_allowlist(feat)

    def test_04_minimum_experience_requirement(self):
        ridge = ExperienceRidge(min_n=MIN_EXPERIENCES_PER_SIDE)
        feat = _feat()
        for i in range(MIN_EXPERIENCES_PER_SIDE - 1):
            ridge.observe(feat, 0.1, -0.1, timestamp="2026-06-19 10:00:00",
                          outcome_end="2026-06-19 11:00:00")
        self.assertFalse(ridge.available())
        self.assertEqual(ridge.predict(feat), (None, None))
        ridge.observe(feat, 0.1, -0.1, timestamp="2026-06-19 10:05:00",
                      outcome_end="2026-06-19 11:05:00")
        self.assertTrue(ridge.available())
        buy, sell = ridge.predict(feat)
        self.assertIsNotNone(buy)
        self.assertIsNotNone(sell)

    def test_05_cold_start_behavior(self):
        pairs, rows = series(4)
        result = replay(pairs, rows, use_learner=True)
        self.assertTrue(all(r["source"] == "cold_start_phase6_engine" for r in result["records"]))
        self.assertTrue(all(r["pred_buy"] is None for r in result["records"]))
        self.assertTrue(all(r["final_decision"] == "WAIT" for r in result["records"]))
        self.assertEqual(result["n_learner_available"], 0)

    def test_06_strict_temporal_boundary(self):
        pairs, rows = series(16)
        result = replay(pairs, rows, use_learner=True, ridge=ExperienceRidge(min_n=2))
        for rec in result["records"]:
            latest = rec["latest_outcome_end"]
            if latest is not None:
                self.assertLess(latest, rec["timestamp"])
            self.assertLess(rec["n_experiences"], 10_000)
        self.assertEqual(result["n_leakage"], 0)

    def test_07_future_experience_exclusion(self):
        times = stamps(16)
        pairs = [pair(t) for t in times]
        rows = [eval_row(t) for t in times]
        result = replay(pairs, rows, use_learner=True, ridge=ExperienceRidge(min_n=2))
        n_at = {r["timestamp"]: r["n_experiences"] for r in result["records"]}
        self.assertEqual(n_at["2026-06-19 10:00:00"], 0)
        self.assertEqual(n_at["2026-06-19 11:00:00"], 0)
        self.assertEqual(n_at["2026-06-19 11:05:00"], 1)
        expected = sum(1 for t in times if outcome_end_for(t) < "2026-06-19 11:05:00")
        self.assertEqual(n_at["2026-06-19 11:05:00"], expected)

    def test_08_online_expanding_window_fitting(self):
        ridge = ExperienceRidge(min_n=2)
        loop = OnlineLoop(ridge)
        times = stamps(16)
        counts = []
        for t in times:
            loop.complete_due(t)
            counts.append(ridge.buy.n)
            loop.enqueue(pair(t), eval_row(t))
        self.assertEqual(counts[0], 0)
        self.assertTrue(all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1)))
        self.assertGreater(counts[-1], counts[12])
        self.assertEqual(counts[-1], sum(1 for t in times if outcome_end_for(t) < times[-1]))

    def test_09_training_sample_audit(self):
        ridge = ExperienceRidge(min_n=2)
        feat = _feat()
        ridge.observe(feat, 0.2, -0.1, timestamp="2026-06-19 10:00:00",
                      outcome_end="2026-06-19 11:00:00")
        ridge.observe(feat, -0.3, 0.4, timestamp="2026-06-19 10:05:00",
                      outcome_end="2026-06-19 11:05:00")
        audit = ridge.audit(fit_timestamp="2026-06-19 11:10:00")
        self.assertEqual(audit["alpha"], RIDGE_ALPHA)
        self.assertEqual(audit["BUY"]["sample_count"], 2)
        self.assertEqual(audit["SELL"]["sample_count"], 2)
        self.assertEqual(audit["BUY"]["earliest"], "2026-06-19 10:00:00")
        self.assertEqual(audit["BUY"]["latest_outcome_end"], "2026-06-19 11:05:00")
        self.assertEqual(audit["feature_columns"], list(PHASE9_LEARNER_FEATURE_ALLOWLIST))
        self.assertEqual(audit["target_column"], "hypothetical_side_net_r")
        self.assertLess(audit["BUY"]["latest_outcome_end"], audit["fit_timestamp"])

    def test_10_riskgate_unchanged(self):
        gate = RiskGate()
        self.assertTrue(gate.wait_only)
        self.assertEqual(gate.champion_id, "no_model")
        src = inspect.getsource(RiskGate.__init__)
        self.assertIn("wait_only: bool = True", src)
        snapshot_protected()
        self.assertEqual(
            PROTECTED_HASHES["src/phase6/risk_gate.py"],
            "a9ffbe3429a0800a23e8a1ffee6af5602e7e29e73a612e477c8f6105507df9d3",
        )

    def test_11_decision_policy_correctness(self):
        self.assertEqual(experience_rule(0.2, 0.1)[0], "BUY")
        self.assertEqual(experience_rule(0.1, 0.2)[0], "SELL")
        self.assertEqual(experience_rule(-0.1, -0.2)[0], "WAIT")
        self.assertEqual(experience_rule(0.2, 0.2)[0], "WAIT")
        self.assertEqual(experience_rule(0.0, -0.1)[0], "WAIT")
        self.assertEqual(experience_rule(-0.1, 0.0)[0], "WAIT")

    def test_12_chronological_replay(self):
        pairs, rows = series(6)
        pairs[0], pairs[1] = pairs[1], pairs[0]
        with self.assertRaisesRegex(RuntimeError, "non-chronological"):
            replay(pairs, rows, use_learner=True)
        ordered, rows = series(16)
        result = replay(ordered, rows, use_learner=True, ridge=ExperienceRidge(min_n=2))
        ts = [r["timestamp"] for r in result["records"]]
        self.assertEqual(ts, sorted(ts))

    def test_13_deterministic_replay(self):
        pairs, rows = series(16)
        a = replay(pairs, rows, use_learner=True, ridge=ExperienceRidge(min_n=2))
        b = replay(pairs, rows, use_learner=True, ridge=ExperienceRidge(min_n=2))
        keys = ("final_decision", "raw_decision", "n_experiences", "pred_buy", "pred_sell", "source")
        for key in keys:
            self.assertEqual([r[key] for r in a["records"]], [r[key] for r in b["records"]])

    def test_14_reproducibility(self):
        pairs, rows = series(16)
        a = replay(pairs, rows, use_learner=True, ridge=ExperienceRidge(min_n=2))
        b = replay(pairs, rows, use_learner=True, ridge=ExperienceRidge(min_n=2))
        self.assertEqual(a["n_fallback"], b["n_fallback"])
        self.assertEqual(a["n_learner_available"], b["n_learner_available"])
        self.assertEqual(a["completed_experiences"], b["completed_experiences"])
        self.assertEqual(a["fit_audit_head"], b["fit_audit_head"])
        frozen = replay(pairs, rows, use_learner=False)
        self.assertTrue(all(r["source"] == "cold_start_phase6_engine" for r in frozen["records"]))
        self.assertEqual(frozen["n_learner_available"], 0)

    def test_15_protected_artifact_integrity(self):
        snap = snapshot_protected()
        self.assertTrue(all(v["unchanged"] for v in snap.values()))
        self.assertEqual(len(snap), len(PROTECTED_HASHES))

    def test_16_ridge_matches_batch_closed_form(self):
        rng = np.random.default_rng(42)
        ridge = ExperienceRidge(min_n=5)
        xs = []
        yb, ys = [], []
        feat0 = _feat()
        names = list(PHASE9_LEARNER_FEATURE_ALLOWLIST)
        for i in range(8):
            feat = {k: float(feat0[k] + 0.01 * rng.normal()) for k in names}
            y_buy = 0.2 * feat["pred_r_rf_BUY"] - 0.1
            y_sell = 0.2 * feat["pred_r_rf_SELL"] + 0.05
            ridge.observe(feat, y_buy, y_sell, timestamp=f"2026-06-19 10:{i:02d}:00",
                          outcome_end=f"2026-06-19 11:{i:02d}:00")
            xs.append([1.0] + [feat[k] for k in names])
            yb.append(y_buy)
            ys.append(y_sell)
        x = np.asarray(xs)
        for y, state in ((np.asarray(yb), ridge.buy), (np.asarray(ys), ridge.sell)):
            a = x.T @ x
            penalty = np.eye(a.shape[0]) * RIDGE_ALPHA
            penalty[0, 0] = 0.0
            beta = np.linalg.solve(a + penalty, x.T @ y)
            np.testing.assert_allclose(ridge._beta(state), beta, rtol=1e-10, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
