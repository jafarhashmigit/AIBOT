"""Deterministic Phase 21 reachability research tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase14.strategy import decide_h13c
from phase16a.constants import FROZEN_CUTS
from phase21.analysis import assert_no_holdout_touch, evaluate_partial
from phase21.constants import (
    BROKER_ORDERS,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    FROZEN_WF3_CUTS,
    HOLDOUT_ACCESSES,
    HOLDOUT_NAME,
    MT5_CONNECTIONS,
    RESEARCH_CUTOFF_UTC,
)
from phase21.integrity import integrity_report, verify_protected_hashes
from phase21.stats import percentile_sorted, summarize_numeric


class Phase21Tests(unittest.TestCase):
    def test_01_frozen_cuts_unchanged(self):
        self.assertEqual(FROZEN_WF3_CUTS["close_ema_low"], FROZEN_CUTS["close_ema_low"])
        self.assertEqual(FROZEN_WF3_CUTS["close_ema_high"], FROZEN_CUTS["close_ema_high"])
        self.assertEqual(FROZEN_WF3_CUTS["q_low"], 25)
        self.assertEqual(FROZEN_WF3_CUTS["q_high"], 75)

    def test_02_percentile_helper(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(percentile_sorted(xs, 0), 1.0)
        self.assertEqual(percentile_sorted(xs, 100), 4.0)
        self.assertAlmostEqual(percentile_sorted(xs, 50), 2.5)

    def test_03_summarize_numeric(self):
        s = summarize_numeric([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(s["n"], 5)
        self.assertEqual(s["min"], 1.0)
        self.assertEqual(s["max"], 5.0)
        self.assertEqual(s["median"], 3.0)
        self.assertIn("q25", s)
        self.assertIn("q99", s)

    def test_04_evaluate_partial_buy_sell(self):
        cuts = FROZEN_WF3_CUTS
        buy_feat = {
            "close_to_ema_20": cuts["close_ema_low"] - 1e-6,
            "ema_9_20_spread": 0.001,
        }
        part = evaluate_partial(buy_feat, {"h1_trend": "up"}, cuts)
        self.assertTrue(part["buy_rule"])
        self.assertFalse(part["sell_rule"])
        action, reason = decide_h13c(buy_feat, {"h1_trend": "up"}, cuts)
        self.assertEqual(action, "BUY")
        self.assertEqual(reason, "selected")

        sell_feat = {
            "close_to_ema_20": cuts["close_ema_high"] + 1e-6,
            "ema_9_20_spread": -0.001,
        }
        part2 = evaluate_partial(sell_feat, {"h1_trend": "down"}, cuts)
        self.assertTrue(part2["sell_rule"])
        action2, _ = decide_h13c(sell_feat, {"h1_trend": "down"}, cuts)
        self.assertEqual(action2, "SELL")

    def test_05_holdout_guard_and_cutoff(self):
        assert_no_holdout_touch()
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertEqual(HOLDOUT_NAME, "xauusd_m5_test.csv")
        self.assertEqual(HOLDOUT_ACCESSES, 0)

    def test_06_safety_constants(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(CANDIDATE_STATUS, "EXPERIMENTAL")
        self.assertEqual(BROKER_ORDERS, 0)
        self.assertEqual(MT5_CONNECTIONS, 0)

    def test_07_integrity_hashes(self):
        report = verify_protected_hashes()
        self.assertTrue(report["all_ok"], msg=str(report))
        integ = integrity_report()
        self.assertFalse(integ["thresholds_modified"])
        self.assertFalse(integ["github_push"])
        self.assertEqual(integ["production_final_action"], "WAIT")

    def test_08_live_not_merged_flag(self):
        integ = integrity_report()
        self.assertFalse(integ["live_shadow_merged_into_historical"])
        self.assertFalse(integ["synthetic_phase19_mixed"])


if __name__ == "__main__":
    unittest.main()
