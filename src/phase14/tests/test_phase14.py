"""Phase 14 offline tests. No holdout. No MT5."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta

from phase14.constants import CHAMPION_STATUS, MAX_DECISION_TIME, RESEARCH_CUTOFF_UTC
from phase14.decision import decide_candidate
from phase14.h1_trend import build_h1_series, h1_trend_at
from phase14.integrity import snapshot_all
from phase14.scoring import stress_net_r
from phase14.strategy import _percentile_sorted, decide_h13c


class Phase14Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_01_champion_remains_no_model(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")

    def test_02_cutoff_constants(self):
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertEqual(MAX_DECISION_TIME, "2026-09-29 17:50:00")

    def test_03_h1_uses_closed_bars_only(self):
        base = datetime(2026, 6, 18, 0, 0, 0)
        rows = []
        for h in range(48):
            t = base + timedelta(hours=h)
            rows.append({
                "time": t.strftime("%Y-%m-%d %H:%M:%S"),
                "open": 1, "high": 2, "low": 0.5, "close": 1.0 + 0.01 * h,
            })
        series = build_h1_series(rows)
        ctx = h1_trend_at(series, "2026-06-19 10:30:00")
        self.assertEqual(ctx["h1_open_time"], "2026-06-19 09:00:00")
        ctx2 = h1_trend_at(series, "2026-06-19 09:30:00")
        self.assertEqual(ctx2["h1_open_time"], "2026-06-19 08:00:00")

    def test_04_decide_h13c_buy_sell_wait(self):
        cuts = {"close_ema_low": -0.2, "close_ema_high": 0.2}
        buy = decide_h13c(
            {"close_to_ema_20": -0.5, "ema_9_20_spread": 0.1},
            {"h1_trend": "up"},
            cuts,
        )
        self.assertEqual(buy[0], "BUY")
        sell = decide_h13c(
            {"close_to_ema_20": 0.5, "ema_9_20_spread": -0.1},
            {"h1_trend": "down"},
            cuts,
        )
        self.assertEqual(sell[0], "SELL")
        wait = decide_h13c(
            {"close_to_ema_20": -0.5, "ema_9_20_spread": -0.1},
            {"h1_trend": "up"},
            cuts,
        )
        self.assertEqual(wait[0], "WAIT")

    def test_05_percentile_independent(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(_percentile_sorted(xs, 25), 1.75)
        self.assertAlmostEqual(_percentile_sorted(xs, 75), 3.25)

    def test_06_stress_net_r_increases_costs(self):
        base = stress_net_r(0.1, 2.0, 1.0)
        stressed = stress_net_r(0.1, 2.0, 1.5)
        self.assertLess(stressed, base)

    def test_07_ready_requires_all_wf_positive(self):
        replication = {
            "exact_economic_match": True,
            "n_independent": 226,
        }
        walk = {
            "pooled": {
                "n": 226,
                "n_days": 50,
                "mean_r": 0.05,
                "bootstrap": {"ci_low": 0.01, "ci_high": 0.1, "p_mean_le_0": 0.01},
            },
            "folds": {
                "WF1": {"n": 60, "mean_r": -0.1},
                "WF2": {"n": 70, "mean_r": 0.1},
                "WF3": {"n": 96, "mean_r": 0.05},
            },
        }
        cost = {
            "1x": {"mean_r_positive": True},
            "1.25x": {"mean_r_positive": True},
            "1.5x": {"mean_r_positive": True},
        }
        stats = {"bootstrap": {"ci_low": 0.01, "p_mean_le_0": 0.01}}
        sufficiency = {"sufficient_for_confirmation": True}
        out = decide_candidate(
            replication=replication,
            walk_forward=walk,
            cost=cost,
            stats=stats,
            sufficiency=sufficiency,
            h1_coverage=1.0,
        )
        self.assertNotEqual(out["status"], "READY_FOR_CONTROLLED_PAPER_RESEARCH")
        self.assertEqual(out["champion_status"], "NO_MODEL")
        self.assertFalse(out["buy_sell_authorized"])

    def test_08_protected_hashes(self):
        snap = snapshot_all()
        for group in snap.values():
            self.assertTrue(all(v["unchanged"] for v in group.values()))
        self.assertNotIn("MetaTrader5", sys.modules)


if __name__ == "__main__":
    unittest.main()
