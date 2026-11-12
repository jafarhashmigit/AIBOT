"""Phase 35 deterministic tests — no MT5, no network."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from phase35.candles import build_m5_candles, floor_m5, ticks_by_m5
from phase35.constants import (
    EXTRA_COST_PER_SIDE_FROZEN,
    H13C_FROZEN_CUTS,
    HOLDOUT_NAME,
    MIN_SPREAD_POINTS_FROZEN,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    file_sha256,
)  # noqa: F401
from phase35.execution import simulate_bidask_trade, simulate_legacy_trade, simulate_stress_trade
from phase35.features import build_features
from phase35.independent import compare_summaries, recompute_from_trades
from phase35.metrics import summarize_trades

UTC = timezone.utc


def _tick(ts: str, bid: float, ask: float) -> dict:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return {
        "timestamp_utc": ts,
        "epoch_ms": int(dt.timestamp() * 1000),
        "bid": bid,
        "ask": ask,
        "spread": ask - bid,
    }


def _synth_path() -> tuple[list[str], dict, dict]:
    """Build a short contiguous synthetic M5 path with ticks."""
    ticks = []
    # 15 bars of ticks
    base = datetime(2026, 7, 8, 10, 0, 0, tzinfo=UTC)
    price = 2400.0
    for b in range(20):
        for s in range(0, 300, 60):
            dt = base.timestamp() + b * 300 + s
            ts = datetime.fromtimestamp(dt, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
            # mild uptrend
            price = 2400.0 + b * 0.5 + s / 300.0 * 0.1
            ticks.append(_tick(ts, price, price + 0.70))
    pack = build_m5_candles(ticks)
    times = [c["time"] for c in pack["candles"]]
    return times, pack["by_time"], ticks_by_m5(ticks)


class TestExecutionSides(unittest.TestCase):
    def test_buy_ask_entry_bid_exit(self):
        times, by_time, tmap = _synth_path()
        # signal at index with room for horizon
        atr = 2.0
        # Force BUY path
        r = simulate_bidask_trade(side="BUY", signal_idx=2, times=times, by_time=by_time, ticks_by_bar=tmap, atr=atr)
        self.assertIn(r["status"], {"PASS", "FAIL", "TIMEOUT", "UNRESOLVED_DATA_GAP"})
        if r["status"] != "UNRESOLVED_DATA_GAP":
            entry_bar = times[3]
            first = tmap[entry_bar][0]
            self.assertEqual(r["entry_fill"], float(first["ask"]))
            # exit should be a bid price from path
            self.assertLessEqual(r["exit_fill"], r["entry_fill"] + 50)  # sanity

    def test_sell_bid_entry_ask_exit(self):
        times, by_time, tmap = _synth_path()
        atr = 2.0
        r = simulate_bidask_trade(side="SELL", signal_idx=2, times=times, by_time=by_time, ticks_by_bar=tmap, atr=atr)
        if r["status"] != "UNRESOLVED_DATA_GAP":
            entry_bar = times[3]
            first = tmap[entry_bar][0]
            self.assertEqual(r["entry_fill"], float(first["bid"]))

    def test_no_midpoint_when_bidask(self):
        times, by_time, tmap = _synth_path()
        r = simulate_bidask_trade(side="BUY", signal_idx=2, times=times, by_time=by_time, ticks_by_bar=tmap, atr=2.0)
        if r["status"] != "UNRESOLVED_DATA_GAP":
            entry_bar = times[3]
            mid = (float(tmap[entry_bar][0]["bid"]) + float(tmap[entry_bar][0]["ask"])) / 2
            self.assertNotAlmostEqual(r["entry_fill"], mid)


class TestGapsAndFabrication(unittest.TestCase):
    def test_missing_hour_unresolved(self):
        times, by_time, tmap = _synth_path()
        # remove a forward bar from by_time to create gap
        drop = times[5]
        by2 = dict(by_time)
        del by2[drop]
        r = simulate_bidask_trade(side="BUY", signal_idx=2, times=times, by_time=by2, ticks_by_bar=tmap, atr=2.0)
        self.assertEqual(r["status"], "UNRESOLVED_DATA_GAP")

    def test_no_fabricated_candles(self):
        ticks = [_tick("2026-07-08 10:00:01", 2400.0, 2400.7), _tick("2026-07-08 10:20:01", 2401.0, 2401.7)]
        pack = build_m5_candles(ticks)
        self.assertFalse(pack["fabricated"])
        self.assertFalse(pack["gap_filled"])
        self.assertEqual(pack["n_candles"], 2)
        self.assertGreater(pack["inferred_missing_m5_slots"], 0)


class TestCostSeparation(unittest.TestCase):
    def test_legacy_uses_frozen_extra(self):
        self.assertEqual(EXTRA_COST_PER_SIDE_FROZEN, 0.05)
        self.assertEqual(MIN_SPREAD_POINTS_FROZEN, 15)

    def test_stress_does_not_alter_primary_object_identity_fields(self):
        times, by_time, tmap = _synth_path()
        ba = simulate_bidask_trade(side="BUY", signal_idx=2, times=times, by_time=by_time, ticks_by_bar=tmap, atr=2.0)
        st = simulate_stress_trade(ba)
        self.assertEqual(st.get("model"), "STRESS")
        if ba.get("status") != "UNRESOLVED_DATA_GAP":
            self.assertEqual(ba.get("extra_cost_added", 0.0), 0.0)


class TestFrozenParams(unittest.TestCase):
    def test_h13c_cuts_frozen(self):
        self.assertEqual(H13C_FROZEN_CUTS["q_low"], 25)
        self.assertEqual(H13C_FROZEN_CUTS["q_high"], 75)
        self.assertIn("close_ema_low", H13C_FROZEN_CUTS)


class TestIndependent(unittest.TestCase):
    def test_recompute(self):
        trades = [
            {"status": "PASS", "net_r": 1.0, "net_pnl": 2.0, "costs": 0.7, "side": "BUY"},
            {"status": "FAIL", "net_r": -1.0, "net_pnl": -2.0, "costs": 0.7, "side": "SELL"},
            {"status": "UNRESOLVED_DATA_GAP", "side": "BUY"},
        ]
        s = summarize_trades(trades)
        indep = recompute_from_trades(trades)
        cmp = compare_summaries(s, indep)
        self.assertTrue(cmp["ok"])
        self.assertEqual(s["n_resolved"], 2)
        self.assertEqual(s["n_unresolved"], 1)


class TestImmutabilityAndSafety(unittest.TestCase):
    def test_protected_hashes(self):
        rel = next(iter(PROTECTED_HASHES))
        self.assertEqual(file_sha256(PROJECT_ROOT / rel), PROTECTED_HASHES[rel])

    def test_production_wait(self):
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        from phase35.constants import HOLDOUT_NAME as HN

        self.assertEqual(HN, "xauusd_m5_test.csv")


class TestFloorM5(unittest.TestCase):
    def test_floor(self):
        self.assertEqual(floor_m5("2026-07-08 10:03:41"), "2026-07-08 10:00:00")


class TestFeaturesNoLeak(unittest.TestCase):
    def test_feature_uses_past_only_seed(self):
        ticks = []
        base = datetime(2026, 7, 8, 8, 0, 0, tzinfo=UTC)
        for b in range(60):
            for s in (0, 120, 240):
                dt = datetime.fromtimestamp(base.timestamp() + b * 300 + s, tz=UTC)
                ts = dt.strftime("%Y-%m-%d %H:%M:%S")
                px = 2400 + b * 0.2
                ticks.append(_tick(ts, px, px + 0.7))
        pack = build_m5_candles(ticks)
        feat = build_features(pack["candles"])
        # early bars should lack ATR
        early = feat["features"][feat["feature_times"][5]]
        late = feat["features"][feat["feature_times"][40]]
        self.assertIsNone(early.get("atr_14"))
        self.assertIsNotNone(late.get("atr_14"))


if __name__ == "__main__":
    unittest.main()
