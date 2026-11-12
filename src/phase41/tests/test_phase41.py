"""Phase 41 tests — frozen specs, execution edges, no live MT5."""

from __future__ import annotations

import unittest

from phase41.constants import (
    CHAMPION_STATUS,
    FROZEN_MEAN_REVERSION,
    H13C_FROZEN_CUTS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    TARGET_DATES,
)
from phase41.execution import simulate_trade
from phase41.qualification import verdict_for_candidate


class TestPolicy(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase41_"))
        self.assertEqual(len(TARGET_DATES), 10)

    def test_frozen_cuts(self):
        self.assertEqual(H13C_FROZEN_CUTS["close_ema_low"], -0.0010069324198160867)
        self.assertEqual(H13C_FROZEN_CUTS["close_ema_high"], 0.0009989244530461683)
        self.assertEqual(FROZEN_MEAN_REVERSION["z_window"], 40)
        self.assertEqual(FROZEN_MEAN_REVERSION["z_entry"], 1.75)
        self.assertEqual(FROZEN_MEAN_REVERSION["rsi_buy_max"], 35.0)
        self.assertEqual(FROZEN_MEAN_REVERSION["rsi_sell_min"], 65.0)


class TestExecution(unittest.TestCase):
    def _ticks(self, bar: str, rows: list[tuple[int, float, float]]):
        return {
            bar: [
                {"epoch_ms": ms, "timestamp_utc": f"{bar[:-2]}{i:02d}", "bid": b, "ask": a}
                for i, (ms, b, a) in enumerate(rows)
            ]
        }

    def test_buy_ask_entry_bid_exit_tp(self):
        times = [f"2026-01-01 12:{m:02d}:00" for m in range(0, 70, 5)]
        # signal at 12:00, entry 12:05
        ticks_by_bar = {}
        for t in times[1:]:
            ticks_by_bar[t] = [
                {"epoch_ms": 1_000, "timestamp_utc": t + ".000", "bid": 100.0, "ask": 100.1},
                {"epoch_ms": 2_000, "timestamp_utc": t + ".001", "bid": 102.0, "ask": 102.1},
            ]
        atr = 1.0  # TP = entry + 1.5
        sim = simulate_trade(
            side="BUY",
            signal_idx=0,
            times=times,
            ticks_by_bar=ticks_by_bar,
            atr=atr,
            adverse_ambiguous=True,
        )
        self.assertEqual(sim["entry_fill"], 100.1)
        self.assertEqual(sim["exit_reason"], "PASS")
        self.assertGreater(sim["net_r"], 0)

    def test_buy_sl_fail(self):
        times = [f"2026-01-01 12:{m:02d}:00" for m in range(0, 70, 5)]
        ticks_by_bar = {}
        for i, t in enumerate(times[1:]):
            if i == 0:
                ticks_by_bar[t] = [
                    {"epoch_ms": 1000, "timestamp_utc": t + ".000", "bid": 100.0, "ask": 100.2},
                    {"epoch_ms": 2000, "timestamp_utc": t + ".001", "bid": 98.0, "ask": 98.2},  # SL at 99.2
                ]
            else:
                ticks_by_bar[t] = [
                    {"epoch_ms": 3000 + i, "timestamp_utc": t + ".000", "bid": 100.0, "ask": 100.2},
                ]
        sim = simulate_trade(
            side="BUY",
            signal_idx=0,
            times=times,
            ticks_by_bar=ticks_by_bar,
            atr=1.0,
            adverse_ambiguous=True,
        )
        self.assertEqual(sim["exit_reason"], "FAIL")
        self.assertLess(sim["net_r"], 0)

    def test_sell_bid_entry(self):
        times = [f"2026-01-01 12:{m:02d}:00" for m in range(0, 70, 5)]
        ticks_by_bar = {}
        for i, t in enumerate(times[1:]):
            if i == 0:
                ticks_by_bar[t] = [
                    {"epoch_ms": 1000, "timestamp_utc": t + ".000", "bid": 100.0, "ask": 100.2},
                    {"epoch_ms": 2000, "timestamp_utc": t + ".001", "bid": 97.0, "ask": 97.2},  # TP for SELL
                ]
            else:
                ticks_by_bar[t] = [
                    {"epoch_ms": 3000 + i, "timestamp_utc": t + ".000", "bid": 99.0, "ask": 99.2},
                ]
        sim = simulate_trade(side="SELL", signal_idx=0, times=times, ticks_by_bar=ticks_by_bar, atr=1.0)
        self.assertEqual(sim["entry_fill"], 100.0)
        self.assertEqual(sim["exit_reason"], "PASS")

    def test_missing_path(self):
        times = [f"2026-01-01 12:{m:02d}:00" for m in range(0, 70, 5)]
        ticks_by_bar = {times[1]: [{"epoch_ms": 1, "timestamp_utc": times[1], "bid": 1.0, "ask": 1.1}]}
        sim = simulate_trade(side="BUY", signal_idx=0, times=times, ticks_by_bar=ticks_by_bar, atr=1.0)
        self.assertEqual(sim["status"], "INSUFFICIENT_TICK_COVERAGE")


class TestVerdict(unittest.TestCase):
    def test_rejected_negative(self):
        result = {
            "summary": {
                "n_signals": 40,
                "n_scored": 40,
                "n_insufficient_coverage": 0,
                "mean_r": -0.2,
                "profit_factor": 0.5,
                "max_dd_r": -5,
            },
            "bootstrap": {},
            "leave_one_date_out": {},
            "scenarios": [],
            "n_independent_dates_with_scores": 8,
        }
        v = verdict_for_candidate(result, indep_ok=True)
        self.assertEqual(v["verdict"], "EDGE_REJECTED")

    def test_blocked_indep(self):
        v = verdict_for_candidate({"summary": {"n_signals": 10, "n_scored": 10}}, indep_ok=False)
        self.assertEqual(v["verdict"], "EXECUTION_MODEL_BLOCKED")


if __name__ == "__main__":
    unittest.main()
