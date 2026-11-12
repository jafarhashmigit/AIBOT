"""Phase47 mandatory tests."""

from __future__ import annotations

import unittest

from phase47.constants import (
    ENGINEERING_DATES,
    EXPECTED_N_OUTCOMES,
    EXPECTED_PER_ACTION,
    FORBIDDEN_VALIDATION_DATES,
    PHASE46_CONTRACT_SHA256_EXPECTED,
    POLICY_THRESHOLDS,
)
from phase47.ev import assert_ev_identity, expected_net_r
from phase47.policy import action_eligible, decide
from phase47.preflight import load_phase46_outcomes, structural_audit, verify_contract_hash
from phase47.splits import assert_no_leakage, walk_forward_folds


class TestPhase46Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_phase46_outcomes()

    def test_contract_hash(self) -> None:
        c = verify_contract_hash()
        self.assertTrue(c["ok"], c)
        self.assertEqual(c["stored"], PHASE46_CONTRACT_SHA256_EXPECTED)

    def test_counts_and_structure(self) -> None:
        s = structural_audit(self.rows)
        self.assertEqual(s["n_rows"], EXPECTED_N_OUTCOMES)
        self.assertEqual(s["action_counts"]["BUY"], EXPECTED_PER_ACTION)
        self.assertEqual(s["action_counts"]["SELL"], EXPECTED_PER_ACTION)
        self.assertEqual(s["action_counts"]["WAIT"], EXPECTED_PER_ACTION)
        self.assertEqual(s["duplicate_keys"], 0)
        self.assertEqual(s["forbidden_hits"], [])
        self.assertTrue(s["chronological_ok"])
        self.assertTrue(s["ok"], s["issues"])

    def test_bid_ask_and_unknown_costs(self) -> None:
        for r in self.rows:
            if r["action"] == "BUY" and r["data_quality_status"] == "OK":
                self.assertEqual(r["entry_fill"], r["entry_ask"])
                self.assertEqual(r["exit_fill"], r["exit_bid"])
                self.assertIsNone(r["commission"])
                self.assertIsNone(r["slippage"])
                sn = r["scenario_nets"]["OBSERVED_BIDASK_ONLY"]
                self.assertAlmostEqual(float(r["gross_pnl"]), float(sn["net_pnl"]))
            if r["action"] == "SELL" and r["data_quality_status"] == "OK":
                self.assertEqual(r["entry_fill"], r["entry_bid"])
                self.assertEqual(r["exit_fill"], r["exit_ask"])
            if r["action"] == "WAIT":
                self.assertEqual(r["net_r"], 0.0)
                self.assertEqual(r["gross_pnl"], 0.0)


class TestSplitsAndEV(unittest.TestCase):
    def test_walk_forward_chrono(self) -> None:
        folds = walk_forward_folds()
        self.assertGreaterEqual(len(folds), 1)
        for f in folds:
            self.assertEqual(set(f["train_dates"]) & set(f["eval_dates"]), set())
            self.assertTrue(max(f["train_dates"]) < min(f["eval_dates"]))

    def test_no_leakage_helper(self) -> None:
        tr = [{"day": "2025-07-02"}, {"day": "2025-07-09"}]
        ev = [{"day": "2025-07-16"}]
        self.assertTrue(assert_no_leakage(tr, ev)["ok"])

    def test_ev_arithmetic(self) -> None:
        ev = expected_net_r(0.6, 1.0, -0.5)
        self.assertAlmostEqual(ev, 0.6 * 1.0 + 0.4 * (-0.5))
        self.assertTrue(assert_ev_identity(0.6, 1.0, -0.5, ev))

    def test_negative_outcomes_in_ev(self) -> None:
        # High win rate can still be negative EV
        ev = expected_net_r(0.7, 0.2, -1.0)
        self.assertLess(ev, 0.0)


class TestPolicy(unittest.TestCase):
    def test_nonpositive_ev_wait(self) -> None:
        buy = {
            "expected_net_r": -0.1,
            "prediction_uncertainty": 0.1,
            "market_familiarity": 0.9,
            "data_quality_status": "OK",
        }
        sell = {
            "expected_net_r": -0.2,
            "prediction_uncertainty": 0.1,
            "market_familiarity": 0.9,
            "data_quality_status": "OK",
        }
        d = decide(buy, sell, buy_stress_ev=-0.15, sell_stress_ev=-0.25)
        self.assertEqual(d["decision"], "WAIT")

    def test_high_uncertainty_wait(self) -> None:
        buy = {
            "expected_net_r": 0.5,
            "prediction_uncertainty": POLICY_THRESHOLDS["max_prediction_uncertainty"] + 0.1,
            "market_familiarity": 0.9,
            "data_quality_status": "OK",
        }
        ok, reasons = action_eligible(buy, stress_ev=0.4)
        self.assertFalse(ok)
        self.assertIn("high_uncertainty", reasons)

    def test_ood_reject(self) -> None:
        buy = {
            "expected_net_r": 0.5,
            "prediction_uncertainty": 0.1,
            "market_familiarity": 0.0,
            "data_quality_status": "OK",
        }
        ok, reasons = action_eligible(buy, stress_ev=0.4)
        self.assertFalse(ok)
        self.assertIn("low_familiarity_ood", reasons)

    def test_buy_wins(self) -> None:
        buy = {
            "expected_net_r": 0.4,
            "prediction_uncertainty": 0.1,
            "market_familiarity": 0.9,
            "data_quality_status": "OK",
        }
        sell = {
            "expected_net_r": 0.2,
            "prediction_uncertainty": 0.1,
            "market_familiarity": 0.9,
            "data_quality_status": "OK",
        }
        d = decide(buy, sell, buy_stress_ev=0.3, sell_stress_ev=0.1)
        self.assertEqual(d["decision"], "BUY")

    def test_sell_wins(self) -> None:
        buy = {
            "expected_net_r": 0.1,
            "prediction_uncertainty": 0.1,
            "market_familiarity": 0.9,
            "data_quality_status": "OK",
        }
        sell = {
            "expected_net_r": 0.5,
            "prediction_uncertainty": 0.1,
            "market_familiarity": 0.9,
            "data_quality_status": "OK",
        }
        d = decide(buy, sell, buy_stress_ev=0.05, sell_stress_ev=0.4)
        self.assertEqual(d["decision"], "SELL")

    def test_thresholds_frozen_present(self) -> None:
        self.assertIn("ev_min_net_r", POLICY_THRESHOLDS)
        self.assertTrue(POLICY_THRESHOLDS["ev_strictly_positive"])

    def test_dates_disjoint(self) -> None:
        self.assertFalse(set(ENGINEERING_DATES) & FORBIDDEN_VALIDATION_DATES)


class TestFullIndependentRecompute(unittest.TestCase):
    """Full 11,211-row independent verification — may take ~30–60s."""

    def test_full_recompute(self) -> None:
        from phase47.preflight import run_preflight

        result = run_preflight()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["independent"]["checked_directional"], EXPECTED_PER_ACTION * 2)
        self.assertEqual(result["independent"]["n_mismatches"], 0)
        self.assertEqual(result["independent"]["wait_nonzero_bad"], 0)


if __name__ == "__main__":
    unittest.main()
