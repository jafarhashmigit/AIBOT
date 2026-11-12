"""Phase 40 tests — coverage acquisition helpers only."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from phase40.constants import CHAMPION_STATUS, PRODUCTION_FINAL_ACTION, RECIPE_ID, TARGET_DATES
from phase40.independent import verify_manifests
from phase40.qualification import decide_verdict
from phase40.storage import sha256_bytes
from phase40.validation import validate_m5, validate_ticks


class TestSafety(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase40_"))
        self.assertEqual(len(TARGET_DATES), 10)


class TestValidation(unittest.TestCase):
    def test_m5_ohlc(self):
        bars = [
            {"time_epoch": 1, "timestamp_utc": "2026-01-01 00:00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5},
            {"time_epoch": 301, "timestamp_utc": "2026-01-01 00:05:00", "open": 1.5, "high": 2, "low": 1, "close": 1.8},
        ]
        self.assertTrue(validate_m5(bars)["pass"])

    def test_ticks_crossed(self):
        bad = [{"bid": 2.0, "ask": 1.0, "timestamp_msc": 1, "timestamp_utc": "2026-01-01 00:00:00.000"}]
        self.assertFalse(validate_ticks(bad)["pass"])

    def test_ticks_ok(self):
        ok = [
            {"bid": 1.0, "ask": 1.1, "timestamp_msc": 1, "timestamp_utc": "2026-01-01 00:00:00.000"},
            {"bid": 1.0, "ask": 1.2, "timestamp_msc": 2, "timestamp_utc": "2026-01-01 00:00:00.001"},
        ]
        self.assertTrue(validate_ticks(ok)["pass"])


class TestHash(unittest.TestCase):
    def test_sha(self):
        self.assertEqual(len(sha256_bytes(b"x")), 64)


class TestVerdict(unittest.TestCase):
    def test_blocked_phase38(self):
        v = decide_verdict(
            phase38_ok=False,
            indep_ok=True,
            alignment={},
            readiness={"H13_C": {"dates_with_any_eligible": 0}, "mean_reversion": {"dates_with_any_eligible": 0}},
            acquisition={},
        )
        self.assertEqual(v["final_verdict"], "DATA_QUALITY_BLOCKED")


class TestIndependentEmptyHour(unittest.TestCase):
    def test_record_count_zero_is_valid(self):
        """Empty-hour chunks declare record_count=0; must not fail via falsy `or`."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "empty.jsonl"
            data.write_bytes(b"")
            dig = sha256_bytes(b"")
            man_dir = root / "manifests"
            man_dir.mkdir()
            man = man_dir / "empty.jsonl.manifest.json"
            man.write_text(
                json.dumps(
                    {
                        "file_path": str(data),
                        "sha256": dig,
                        "record_count": 0,
                    }
                ),
                encoding="utf-8",
            )
            with patch("phase40.independent.MANIFESTS", man_dir):
                out = verify_manifests()
            self.assertTrue(out["ok"])
            self.assertTrue(out["results"][0]["count_ok"])
            self.assertEqual(out["results"][0]["reload_n"], 0)


if __name__ == "__main__":
    unittest.main()
