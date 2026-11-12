"""Phase 38 unit tests — synthetic data only inside tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from phase38.acquisition import load_state, save_state
from phase38.constants import CHAMPION_STATUS, PRODUCTION_FINAL_ACTION, RECIPE_ID, STATE_DIR
from phase38.diagnostics import spread_diagnostics
from phase38.qualification import decide_verdict
from phase38.safety import audit_phase38
from phase38.storage import sha256_bytes
from phase38.validation import validate_m5_bars, validate_ticks
from phase38.utc_check import assert_utc_storage_stamp

UTC = timezone.utc


class TestSafety(unittest.TestCase):
    def test_audit_and_policy(self):
        self.assertTrue(audit_phase38()["pass"])
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase38_"))


class TestUtc(unittest.TestCase):
    def test_utc_stamp(self):
        self.assertTrue(assert_utc_storage_stamp("2026-02-16 12:00:00"))
        with self.assertRaises(ValueError):
            assert_utc_storage_stamp("not-a-stamp")


class TestM5Validation(unittest.TestCase):
    def test_chrono_dup_gap_ohlc(self):
        bars = [
            {"time_epoch": 1000, "timestamp_utc": "2026-01-01 00:00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5},
            {"time_epoch": 1300, "timestamp_utc": "2026-01-01 00:05:00", "open": 1.5, "high": 2, "low": 1, "close": 1.8},
            {"time_epoch": 1900, "timestamp_utc": "2026-01-01 00:15:00", "open": 1.8, "high": 2.1, "low": 1.7, "close": 2.0},
        ]
        v = validate_m5_bars(bars)
        self.assertEqual(v["n_accepted"], 3)
        self.assertGreaterEqual(v["unexpected_gaps_lt_30m"], 1)
        bad = [{"time_epoch": 1, "timestamp_utc": "2026-01-01 00:00:00", "open": 2, "high": 1, "low": 0.5, "close": 1.5}]
        self.assertFalse(validate_m5_bars(bad)["pass"])


class TestTicks(unittest.TestCase):
    def test_bid_ask_and_crossed(self):
        ok = [
            {"bid": 1.0, "ask": 1.1, "timestamp_msc": 1000, "timestamp_utc": "2026-01-01 00:00:00.000"},
            {"bid": 1.0, "ask": 1.2, "timestamp_msc": 1100, "timestamp_utc": "2026-01-01 00:00:00.100"},
        ]
        v = validate_ticks(ok)
        self.assertTrue(v["pass"])
        crossed = [{"bid": 2.0, "ask": 1.0, "timestamp_msc": 1000, "timestamp_utc": "2026-01-01 00:00:00.000"}]
        self.assertFalse(validate_ticks(crossed)["pass"])


class TestSpread(unittest.TestCase):
    def test_spread_stats(self):
        ticks = [
            {"bid": 1.0, "ask": 1.2, "timestamp_utc": "2026-01-05 12:00:00.000"},
            {"bid": 1.0, "ask": 1.3, "timestamp_utc": "2026-01-05 13:00:00.000"},
        ]
        d = spread_diagnostics(ticks)
        self.assertAlmostEqual(d["overall"]["median"], 0.25)


class TestHashAndResume(unittest.TestCase):
    def test_sha256(self):
        self.assertEqual(len(sha256_bytes(b"abc")), 64)

    def test_resume_state_reconciles_disk(self):
        loaded = load_state()
        self.assertTrue(loaded.get("reconciled_from_disk"))
        self.assertIsInstance(loaded.get("completed"), dict)
        self.assertIsInstance(loaded.get("pending"), list)
        # completed days must exist on disk
        from phase38.acquisition import _m5_done, _ticks_done

        for day in loaded.get("completed", {}):
            self.assertTrue(_m5_done(day) and _ticks_done(day), day)


class TestQualification(unittest.TestCase):
    def test_ready_path(self):
        g = decide_verdict(
            {
                "connection": {"status": "connected_readonly"},
                "coverage": {"probes": [1]},
                "acquisition": {"completed_days": ["a", "b", "c", "d", "e"]},
                "independent": {"ok": True},
                "counts": {"m5_record_count": 10, "tick_record_count": 10},
                "safety": {"pass": True},
            }
        )
        self.assertEqual(g["final_verdict"], "CANONICAL_DATA_ENGINE_READY")

    def test_blocked_on_indep_fail(self):
        g = decide_verdict(
            {
                "connection": {"status": "connected_readonly"},
                "coverage": {"probes": [1]},
                "acquisition": {"completed_days": ["a"]},
                "independent": {"ok": False},
                "counts": {"m5_record_count": 10, "tick_record_count": 10},
                "safety": {"pass": True},
            }
        )
        self.assertEqual(g["final_verdict"], "DATA_QUALITY_BLOCKED")


if __name__ == "__main__":
    unittest.main()
