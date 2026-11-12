"""Phase 39 tests — execution reality, no strategy tuning."""

from __future__ import annotations

import unittest

from phase39.constants import (
    CHAMPION_STATUS,
    FROZEN_MEAN_REVERSION,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
)
from phase39.execution import apply_cost_scenario, simulate_trade
from phase39.frozen_spec import verify_and_freeze
from phase39.metrics import summarize
from phase39.qualification import verdict_for_candidate


class TestSafety(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase39_"))


class TestFrozenSpec(unittest.TestCase):
    def test_mr_params(self):
        self.assertEqual(FROZEN_MEAN_REVERSION["z_window"], 40)
        self.assertEqual(FROZEN_MEAN_REVERSION["z_entry"], 1.75)
        spec = verify_and_freeze()
        self.assertTrue(spec["spec_ok"], spec.get("discrepancies"))


class TestExecution(unittest.TestCase):
    def _ticks(self, bar: str, prices: list[tuple[float, float]], start_ms: int = 1_000_000):
        out = []
        for i, (bid, ask) in enumerate(prices):
            out.append(
                {
                    "bid": bid,
                    "ask": ask,
                    "epoch_ms": start_ms + i * 10,
                    "timestamp_utc": f"2026-01-01 12:00:00.{i:03d}",
                    "timestamp_msc": start_ms + i * 10,
                }
            )
        return {bar: out}

    def test_buy_ask_entry_bid_exit_tp(self):
        # 13 bars: signal + 12 horizon; TP hit on entry bar
        times = [f"2026-01-01 12:{m:02d}:00" for m in range(0, 65, 5)][:13]
        ticks_by_bar = {}
        for i, t in enumerate(times):
            if i == 0:
                continue
            if i == 1:
                ticks_by_bar[t] = self._ticks(t, [(100.0, 100.2), (101.8, 102.0)], start_ms=1_000_000)[t]
            else:
                ticks_by_bar[t] = self._ticks(t, [(101.0, 101.1)], start_ms=1_000_000 + i * 1000)[t]
        atr = 1.0  # TP = entry_ask + 1.5 = 101.7
        sim = simulate_trade(side="BUY", signal_idx=0, times=times, ticks_by_bar=ticks_by_bar, atr=atr)
        self.assertEqual(sim["entry_fill"], 100.2)
        self.assertEqual(sim["exit_reason"], "PASS")
        self.assertGreater(sim["net_r"], 0)

    def test_missing_ticks_insufficient(self):
        times = [f"2026-01-01 12:{m:02d}:00" for m in range(0, 65, 5)][:13]
        ticks_by_bar = {times[1]: self._ticks(times[1], [(100.0, 100.1)])[times[1]]}
        sim = simulate_trade(side="BUY", signal_idx=0, times=times, ticks_by_bar=ticks_by_bar, atr=1.0)
        self.assertEqual(sim["status"], "INSUFFICIENT_TICK_COVERAGE")

    def test_cost_scenario(self):
        trade = {"net_pnl": 1.0, "net_r": 1.0, "initial_risk": 1.0, "entry_spread": 0.1, "exit_spread": 0.1}
        adj = apply_cost_scenario(trade, slippage_per_side=0.05, commission_per_side=0.05, spread_widen_mult=1.0)
        self.assertAlmostEqual(adj["scenario_extra_cost_usd"], 0.2)
        self.assertAlmostEqual(adj["scenario_net_r"], 0.8)


class TestMetrics(unittest.TestCase):
    def test_summarize_empty(self):
        s = summarize([])
        self.assertEqual(s["n_scored"], 0)


class TestVerdict(unittest.TestCase):
    def test_insufficient(self):
        v = verdict_for_candidate(
            {"summary": {"n_scored": 2, "n_signals": 5, "n_insufficient_coverage": 3, "mean_r": 0.1}, "bootstrap": {}, "n_independent_dates_with_scores": 1, "scenarios": []},
            indep_ok=True,
        )
        self.assertEqual(v["verdict"], "INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
