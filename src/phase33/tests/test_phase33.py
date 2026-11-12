"""Deterministic Phase 33 unit tests — no network, no MT5."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from phase33.candle_builder import build_m5_candles, floor_m5
from phase33.constants import (
    EXTRA_COST_PER_SIDE,
    HOLDOUT_NAME,
    MIN_SPREAD_POINTS,
    POINT_SIZE,
    PRODUCTION_FINAL_ACTION,
    PROTECTED_HASHES,
    RESEARCH_CUTOFF_UTC,
    file_sha256,
)
from phase33.execution_comparison import (
    buy_entry_ask,
    buy_exit_bid,
    classify_intrabar_ambiguity,
    sell_entry_bid,
    sell_exit_ask,
)
from phase33.preflight import verify_protected_hashes
from phase33.raw_data_validation import validate_ticks
from phase33.sample_acquisition import bi5_url, decode_ticks
from phase33.spread_analysis import analyze_spreads
from phase33.timestamp_validation import validate_timestamps

UTC = timezone.utc


def _tick(ts: str, bid: float, ask: float) -> dict:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return {
        "timestamp_utc": ts,
        "epoch_ms": int(dt.timestamp() * 1000),
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2.0,
        "spread": ask - bid,
        "ask_volume": 1.0,
        "bid_volume": 1.0,
    }


class TestBidAskValidity(unittest.TestCase):
    def test_bid_ask_valid(self):
        ticks = [_tick("2026-02-17 08:00:01", 2900.0, 2900.15)]
        r = validate_ticks(ticks)
        self.assertTrue(r["pass"])
        self.assertEqual(r["checks"]["bid_gt_ask"], 0)

    def test_bid_gt_ask_fails(self):
        ticks = [_tick("2026-02-17 08:00:01", 2900.20, 2900.10)]
        r = validate_ticks(ticks)
        self.assertFalse(r["pass"])
        self.assertEqual(r["checks"]["bid_gt_ask"], 1)


class TestSpreadCalculation(unittest.TestCase):
    def test_spread(self):
        ticks = [
            _tick("2026-02-17 08:00:01", 100.0, 100.15),
            _tick("2026-02-17 08:00:02", 100.0, 100.25),
        ]
        r = analyze_spreads(ticks)
        self.assertTrue(r["pass"])
        self.assertAlmostEqual(r["overall_usd"]["median"], 0.20, places=6)
        self.assertAlmostEqual(r["overall_points"]["median"], 20.0, places=6)


class TestPricePrecision(unittest.TestCase):
    def test_point_size(self):
        self.assertEqual(POINT_SIZE, 0.01)
        self.assertEqual(MIN_SPREAD_POINTS * POINT_SIZE, 0.15)


class TestUtcAndDst(unittest.TestCase):
    def test_utc_conversion_and_dst_probes(self):
        # US DST 2026 starts Mar 8; Mar 10 should be EDT
        ticks = [
            _tick("2026-03-10 12:00:00", 2900.0, 2900.12),
            _tick("2026-03-10 12:00:01", 2900.0, 2900.12),
        ]
        candles = [{"timestamp_utc": "2026-03-10 12:00:00"}]
        r = validate_timestamps(ticks, candles)
        self.assertTrue(r["pass"])
        probe = next(p for p in r["dst_probes"] if p["day"] == "2026-03-10")
        self.assertTrue(probe["us_dst"])


class TestDuplicatesAndMissing(unittest.TestCase):
    def test_duplicates_flagged(self):
        t = _tick("2026-02-17 08:00:01", 2900.0, 2900.1)
        r = validate_ticks([t, dict(t)])
        self.assertEqual(r["checks"]["duplicate_epoch_extra_rows"], 1)

    def test_unordered_fails(self):
        ticks = [
            _tick("2026-02-17 08:00:02", 2900.0, 2900.1),
            _tick("2026-02-17 08:00:01", 2900.0, 2900.1),
        ]
        r = validate_ticks(ticks)
        self.assertFalse(r["pass"])


class TestM5CandleConstruction(unittest.TestCase):
    def test_floor_m5(self):
        self.assertEqual(floor_m5("2026-02-17 08:03:41"), "2026-02-17 08:00:00")
        self.assertEqual(floor_m5("2026-02-17 08:05:00"), "2026-02-17 08:05:00")

    def test_bid_ask_ohlc_separation(self):
        ticks = [
            _tick("2026-02-17 08:00:01", 100.0, 100.20),
            _tick("2026-02-17 08:01:00", 100.5, 100.70),
            _tick("2026-02-17 08:04:59", 99.5, 99.70),
        ]
        out = build_m5_candles(ticks)
        self.assertTrue(out["report"]["pass"])
        self.assertTrue(out["report"]["bid_ask_ohlc_separated"])
        c = out["candles"][0]
        self.assertEqual(c["bid_open"], 100.0)
        self.assertEqual(c["bid_high"], 100.5)
        self.assertEqual(c["bid_low"], 99.5)
        self.assertEqual(c["bid_close"], 99.5)
        self.assertEqual(c["ask_open"], 100.20)
        self.assertEqual(c["ask_high"], 100.70)
        self.assertEqual(c["ask_low"], 99.70)
        self.assertEqual(c["ask_close"], 99.70)
        # Must not mix sides
        self.assertNotEqual(c["bid_high"], c["ask_high"])


class TestExecutionSides(unittest.TestCase):
    def test_buy_entry_exit(self):
        self.assertEqual(buy_entry_ask(1900.25), 1900.25)
        self.assertEqual(buy_exit_bid(1900.10), 1900.10)

    def test_sell_entry_exit(self):
        self.assertEqual(sell_entry_bid(1900.10), 1900.10)
        self.assertEqual(sell_exit_ask(1900.25), 1900.25)

    def test_tp_sl_semantics_and_ambiguity(self):
        amb = classify_intrabar_ambiguity()
        self.assertEqual(amb["classification"], "INTRABAR_ORDERING_AMBIGUOUS")
        self.assertIn("BUY_TP", amb["tp_sl_semantics"])
        self.assertIn("SELL_SL", amb["tp_sl_semantics"])
        self.assertFalse(amb["intrabar_path_known"])


class TestCutoffAndArtifacts(unittest.TestCase):
    def test_cutoff_enforcement_in_validation(self):
        ticks = [_tick("2026-09-29 19:00:00", 2900.0, 2900.1)]
        r = validate_ticks(ticks)
        self.assertFalse(r["pass"])
        self.assertEqual(r["checks"]["after_cutoff"], 1)
        self.assertLess(RESEARCH_CUTOFF_UTC, "2026-09-29 19:00:00")

    def test_holdout_name_forbidden(self):
        self.assertEqual(HOLDOUT_NAME, "xauusd_m5_test.csv")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")

    def test_protected_artifact_integrity(self):
        r = verify_protected_hashes()
        self.assertTrue(r["intact"], msg=str(r))
        # sanity: hash helper matches
        from pathlib import Path
        from phase33.constants import PROJECT_ROOT

        sample_rel = next(iter(PROTECTED_HASHES))
        p = PROJECT_ROOT / sample_rel
        self.assertEqual(file_sha256(p), PROTECTED_HASHES[sample_rel])


class TestBi5Url(unittest.TestCase):
    def test_zero_based_month(self):
        url = bi5_url("2026-03-10", 12)
        self.assertIn("/2026/02/10/12h_ticks.bi5", url)
        self.assertIn("XAUUSD", url)

    def test_decode_empty(self):
        self.assertEqual(decode_ticks(b"", day="2026-02-17", hour=8), [])


class TestExtraCostConstant(unittest.TestCase):
    def test_extra_cost(self):
        self.assertEqual(EXTRA_COST_PER_SIDE, 0.05)


if __name__ == "__main__":
    unittest.main()
