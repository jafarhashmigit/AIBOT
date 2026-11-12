"""Focused Phase 37 tests — data qualification only; no strategy eval."""

from __future__ import annotations

import ast
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from phase37.bars import analyze_m5_bars, rates_to_bars
from phase37.cache import load_jsonl, save_bars_sample, save_ticks_sample
from phase37.connection import package_available, terminal_exists
from phase37.constants import (
    CHAMPION_STATUS,
    PHASE37_PROHIBITED_MT5_API,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    SRC_DIR,
)
from phase37.independent import validate_bars_reload, validate_ticks_reload
from phase37.qualification import apply_qualification
from phase37.safety import audit_phase37_sources
from phase37.ticks import analyze_ticks
from phase37.utc_dst import interpret_rate_epoch

UTC = timezone.utc


class TestSafety(unittest.TestCase):
    def test_no_order_apis_in_phase37(self):
        audit = audit_phase37_sources()
        self.assertTrue(audit["pass"], audit.get("prohibited_hits"))
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")

    def test_ast_denylist_covers_order_send(self):
        self.assertIn("order_send", PHASE37_PROHIBITED_MT5_API)
        self.assertIn("buy", PHASE37_PROHIBITED_MT5_API)
        # ensure runner source doesn't mention order_send
        text = (SRC_DIR / "phase37" / "run_phase37.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        self.assertNotIn("order_send", ast.dump(tree))


class TestPackageAndTerminal(unittest.TestCase):
    def test_package_probe(self):
        pkg = package_available()
        self.assertIn("available", pkg)

    def test_terminal_path(self):
        # Soft: path may exist on this machine
        self.assertIsInstance(terminal_exists(), bool)


class TestBarsAndGaps(unittest.TestCase):
    def test_ohlc_and_gaps(self):
        bars = [
            {
                "time_epoch": 1000,
                "time_utc": "2026-01-01 00:00:00",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 1,
                "spread": 1,
                "real_volume": 0,
            },
            {
                "time_epoch": 1300,
                "time_utc": "2026-01-01 00:05:00",
                "open": 1.5,
                "high": 2.0,
                "low": 1.0,
                "close": 1.8,
                "tick_volume": 1,
                "spread": 1,
                "real_volume": 0,
            },
            {
                "time_epoch": 1900,
                "time_utc": "2026-01-01 00:15:00",
                "open": 1.8,
                "high": 2.1,
                "low": 1.7,
                "close": 2.0,
                "tick_volume": 1,
                "spread": 1,
                "real_volume": 0,
            },
        ]
        a = analyze_m5_bars(bars)
        self.assertTrue(a["pass_ohlc"])
        self.assertTrue(a["pass_chrono"])
        self.assertGreaterEqual(a["unexpected_gaps_lt_30m"], 1)


class TestTicksBidAsk(unittest.TestCase):
    def test_spread_stats(self):
        rows = [
            {
                "time_epoch": 1,
                "time_msc": 1000,
                "timestamp_utc": "2026-01-01 00:00:00.000",
                "bid": 100.0,
                "ask": 100.2,
                "last": 0.0,
                "volume": 0,
                "volume_real": 0.0,
                "flags": 0,
                "spread": 0.2,
            },
            {
                "time_epoch": 1,
                "time_msc": 1100,
                "timestamp_utc": "2026-01-01 00:00:00.100",
                "bid": 100.0,
                "ask": 100.3,
                "last": 0.0,
                "volume": 0,
                "volume_real": 0.0,
                "flags": 0,
                "spread": 0.3,
            },
        ]
        a = analyze_ticks(rows)
        self.assertTrue(a["bid_available"])
        self.assertTrue(a["ask_available"])
        self.assertTrue(a["pass_spread"])
        self.assertAlmostEqual(a["spread_median"], 0.25)

    def test_crossed_fails(self):
        rows = [
            {
                "time_epoch": 1,
                "time_msc": 1000,
                "timestamp_utc": "2026-01-01 00:00:00.000",
                "bid": 2.0,
                "ask": 1.0,
                "last": 0.0,
                "volume": 0,
                "volume_real": 0.0,
                "flags": 0,
                "spread": -1.0,
            }
        ]
        a = analyze_ticks(rows)
        self.assertFalse(a["pass_spread"])
        self.assertEqual(a["crossed_bid_gt_ask"], 1)


class TestUtc(unittest.TestCase):
    def test_interpret_epoch(self):
        # 2026-03-29 00:00 UTC approx
        epoch = int(datetime(2026, 3, 29, 0, 0, tzinfo=UTC).timestamp())
        info = interpret_rate_epoch(epoch)
        self.assertIn("python_fromtimestamp_utc", info)
        self.assertTrue(info["python_fromtimestamp_utc"].startswith("2026-03-29"))


class TestCacheAndIndependent(unittest.TestCase):
    def test_manifest_and_reload(self):
        bars = [
            {
                "time_epoch": 1000,
                "time_utc": "2026-01-01 00:00:00",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 1,
                "spread": 1,
                "real_volume": 0,
            }
        ]
        analysis = analyze_m5_bars(bars)
        with tempfile.TemporaryDirectory() as td:
            # redirect by writing via save into real dirs would pollute; test load_jsonl + validate directly
            p = Path(td) / "bars.jsonl"
            p.write_text(
                '{"time_epoch": 1000, "time_utc": "2026-01-01 00:00:00", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "tick_volume": 1, "spread": 1, "real_volume": 0}\n',
                encoding="utf-8",
            )
            vr = validate_bars_reload(p, analysis, 1)
            self.assertTrue(vr["ok"], vr.get("mismatches"))
            ticks = [
                {
                    "time_epoch": 1,
                    "time_msc": 1000,
                    "timestamp_utc": "2026-01-01 00:00:00.000",
                    "bid": 1.0,
                    "ask": 1.1,
                    "last": 0.0,
                    "volume": 0,
                    "volume_real": 0.0,
                    "flags": 0,
                    "spread": 0.1,
                }
            ]
            ta = analyze_ticks(ticks)
            tp = Path(td) / "ticks.jsonl"
            import json

            tp.write_text(json.dumps(ticks[0], sort_keys=True) + "\n", encoding="utf-8")
            tr = validate_ticks_reload(tp, ta, 1)
            self.assertTrue(tr["ok"], tr.get("mismatches"))


class TestQualification(unittest.TestCase):
    def test_unavailable(self):
        g = apply_qualification(
            {
                "preflight": {"terminal_exists": False, "package": {"available": False}, "connection": {"status": "unavailable"}, "symbol": {"status": "skipped"}},
                "m5_tests": {},
                "tick_tests": {},
                "speed": {},
                "range_probe": {},
                "independent_validation": {"ok": True},
            }
        )
        self.assertEqual(g["final_verdict"], "MT5_UNAVAILABLE")

    def test_recipe_id(self):
        self.assertTrue(RECIPE_ID.startswith("phase37_"))


if __name__ == "__main__":
    unittest.main()
