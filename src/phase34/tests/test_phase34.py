"""Deterministic Phase 34 tests — no network required for unit tests."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from phase34.bi5 import bi5_url, decode_ticks
from phase34.constants import (
    HOLDOUT_NAME,
    POINT_SIZE,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    RESEARCH_CUTOFF_UTC,
    file_sha256,
    select_trading_days,
)
from phase34.cost_reconciliation import reconcile_costs
from phase34.dst_validation import eu_dst, us_dst, validate_utc_dst
from phase34.immutability import check_phase33_immutability
from phase34.quality import validate_ticks
from phase34.spread_analysis import analyze_spreads, independent_recompute_from_jsonl

UTC = timezone.utc


def _tick(ts: str, bid: float, ask: float) -> dict:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return {
        "timestamp_utc": ts,
        "epoch_ms": int(dt.timestamp() * 1000),
        "bid": bid,
        "ask": ask,
        "spread": ask - bid,
        "ask_volume": 1.0,
        "bid_volume": 1.0,
    }


class TestBi5(unittest.TestCase):
    def test_zero_based_month(self):
        self.assertIn("/2026/02/10/12h_ticks.bi5", bi5_url("2026-03-10", 12))

    def test_decode_empty(self):
        self.assertEqual(decode_ticks(b"", day="2026-02-17", hour=8), [])


class TestBidAskIntegrity(unittest.TestCase):
    def test_ok(self):
        r = validate_ticks([_tick("2026-02-17 08:00:01", 2900.0, 2900.7)])
        self.assertTrue(r["pass"])

    def test_crossed_fails(self):
        r = validate_ticks([_tick("2026-02-17 08:00:01", 2900.8, 2900.1)])
        self.assertFalse(r["pass"])


class TestTimestampsDst(unittest.TestCase):
    def test_us_dst_boundaries(self):
        pre = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
        post = datetime(2026, 3, 9, 12, 0, tzinfo=UTC)
        self.assertFalse(us_dst(pre))
        self.assertTrue(us_dst(post))

    def test_eu_dst_boundaries(self):
        pre = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)
        post = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
        self.assertFalse(eu_dst(pre))
        self.assertTrue(eu_dst(post))

    def test_validate_utc(self):
        ticks = [_tick("2026-03-09 12:00:00", 1.0, 1.1), _tick("2026-03-09 12:00:01", 1.0, 1.1)]
        r = validate_utc_dst(ticks, ["2026-03-09"])
        self.assertTrue(r["pass"])


class TestDuplicatesMissing(unittest.TestCase):
    def test_duplicates_counted(self):
        t = _tick("2026-02-17 08:00:01", 1.0, 1.1)
        r = validate_ticks([t, dict(t)])
        self.assertEqual(r["checks"]["duplicate_epoch_extra_rows"], 1)
        self.assertIn("retain_all", r["checks"]["duplicate_policy"])


class TestDaySelection(unittest.TestCase):
    def test_deterministic(self):
        a = select_trading_days(20)
        b = select_trading_days(20)
        self.assertEqual(a, b)
        self.assertLessEqual(len(a), 20)
        self.assertTrue(all(d <= RESEARCH_CUTOFF_UTC[:10] for d in a))
        # Forced DST-adjacent present when n=20
        self.assertIn("2026-03-09", a)
        self.assertIn("2026-03-30", a)


class TestSpreadAndCost(unittest.TestCase):
    def test_spread_points(self):
        ticks = [_tick("2026-02-17 08:00:01", 100.0, 100.70), _tick("2026-02-17 08:00:02", 100.0, 100.70)]
        r = analyze_spreads(ticks)
        self.assertAlmostEqual(r["overall_usd"]["median"], 0.70, places=6)
        self.assertAlmostEqual(r["overall_points"]["median"], 70.0, places=6)
        self.assertIn("15", r["pct_observations_above_points"])

    def test_cost_no_double_count(self):
        spreads = analyze_spreads([_tick("2026-02-17 08:00:01", 100.0, 100.70)])
        c = reconcile_costs(spreads)
        self.assertFalse(c["frozen_assumptions"]["double_counting_spread"])
        self.assertFalse(c["frozen_assumptions"]["labels_modified"])
        self.assertIn("baseline", c["scenarios"])


class TestIndependentRecompute(unittest.TestCase):
    def test_jsonl_recompute(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "d.jsonl"
            rows = [_tick("2026-02-17 08:00:01", 100.0, 100.50), _tick("2026-02-17 08:00:02", 100.0, 100.70)]
            p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            out = independent_recompute_from_jsonl([p])
            self.assertEqual(out["n"], 2)
            self.assertAlmostEqual(out["median"], 0.60, places=6)


class TestHashAndResumeSemantics(unittest.TestCase):
    def test_hash_stable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.bi5"
            p.write_bytes(b"abc")
            self.assertEqual(file_sha256(p), hashlib.sha256(b"abc").hexdigest())

    def test_protected_and_phase33(self):
        r = check_phase33_immutability()
        self.assertTrue(r["protected_artifacts_intact"])
        self.assertTrue(r["phase33_immutable_ok"])
        sample = next(iter(PROTECTED_HASHES))
        self.assertEqual(file_sha256(PROJECT_ROOT / sample), PROTECTED_HASHES[sample])

    def test_holdout_name(self):
        self.assertEqual(HOLDOUT_NAME, "xauusd_m5_test.csv")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")


class TestCutoff(unittest.TestCase):
    def test_after_cutoff_fails_quality(self):
        r = validate_ticks([_tick("2026-09-29 19:00:00", 1.0, 1.1)])
        self.assertFalse(r["pass"])


if __name__ == "__main__":
    unittest.main()
