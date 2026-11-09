"""Phase 24 offline tests — no MT5, Discord, installs, OCI, or holdout."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase24.adapter import (
    FixtureProvider,
    normalize_candle,
    validate_candle,
    validate_series,
)
from phase24.constants import (
    FINAL_DECISION,
    FIXTURES_DIR,
    HOLDOUT_NAME,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
)
from phase24.integrity import protected_hashes_report
from phase24.parity import assert_no_holdout_touch, run_algospecial_parity
from phase24.providers import provider_qualification


class Phase24Tests(unittest.TestCase):
    def test_01_adapter_rejects_incomplete_and_bad_ohlc(self):
        good = normalize_candle(
            symbol="XAUUSD",
            timeframe="M5",
            timestamp_utc="2026-02-16 12:55:00",
            open_=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            source_id="fixture",
        )
        self.assertEqual(validate_candle(good, as_of_utc="2026-02-16 13:00:01"), [])
        incomplete = validate_candle(good, as_of_utc="2026-02-16 13:00:00")
        self.assertTrue(any(i.code == "INCOMPLETE" for i in incomplete))
        bad = normalize_candle(
            symbol="XAUUSD",
            timeframe="M5",
            timestamp_utc="2026-02-16 12:55:00",
            open_=100.0,
            high=99.0,
            low=98.0,
            close=100.5,
            source_id="fixture",
        )
        self.assertTrue(any(i.code == "OHLC_INCONSISTENT" for i in validate_candle(bad)))

    def test_02_duplicate_and_out_of_order(self):
        a = normalize_candle(
            symbol="XAUUSD",
            timeframe="M5",
            timestamp_utc="2026-02-16 12:55:00",
            open_=1,
            high=2,
            low=0.5,
            close=1.5,
            source_id="f",
        )
        b = normalize_candle(
            symbol="XAUUSD",
            timeframe="M5",
            timestamp_utc="2026-02-16 12:55:00",
            open_=1,
            high=2,
            low=0.5,
            close=1.6,
            source_id="f",
        )
        res = validate_series([a, b], as_of_utc="2026-02-16 13:00:01")
        self.assertEqual(res["accepted_count"], 1)
        self.assertTrue(any(i["code"] == "DUPLICATE" for i in res["issues"]))

    def test_03_fixture_provider_offline(self):
        c = normalize_candle(
            symbol="XAUUSD",
            timeframe="M5",
            timestamp_utc="2026-02-16 13:00:00",
            open_=1,
            high=2,
            low=0.5,
            close=1.2,
            source_id="f",
        )
        p = FixtureProvider("f", [c])
        self.assertEqual(len(p.fetch_completed_m5(start_utc="2026-02-16 00:00:00", end_utc="2026-02-16 23:59:59")), 1)
        self.assertEqual(p.health()["live"], False)

    def test_04_holdout_guard(self):
        assert_no_holdout_touch()
        with self.assertRaises(RuntimeError):
            assert_no_holdout_touch(Path(HOLDOUT_NAME))
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")

    def test_05_algospecial_parity_fails(self):
        self.assertTrue((FIXTURES_DIR / "algospecial_xauusd_m5_2026-02-16_17.json").is_file())
        self.assertTrue((FIXTURES_DIR / "mt5_reference_xauusd_m5_2026-02-16_17.json").is_file())
        report = run_algospecial_parity()
        self.assertEqual(report["parity_result"], "FAIL")
        self.assertFalse(report["holdout_accessed"])
        self.assertFalse(report["h13c_thresholds_recalibrated"])
        self.assertGreater(report["ohlc_abs_diff"]["close"]["p50"], 0.5)

    def test_06_provider_decision_blocked(self):
        q = provider_qualification()
        self.assertEqual(q["final_decision"], "PROVIDER_BLOCKED")
        self.assertEqual(FINAL_DECISION, "PROVIDER_BLOCKED")
        self.assertIsNone(q["selected_provider"])
        self.assertFalse(q["any_qualified"])

    def test_07_safety_and_hashes(self):
        h = protected_hashes_report()
        self.assertTrue(h["all_ok"])
        self.assertTrue(h["frozen_thresholds_intact"])
        self.assertEqual(h["safety"]["production_final_action"], PRODUCTION_FINAL_ACTION)
        self.assertEqual(h["safety"]["mt5_connections"], 0)
        self.assertEqual(h["safety"]["discord_messages_sent"], 0)
        self.assertEqual(h["safety"]["broker_orders"], 0)

    def test_08_docs_exist(self):
        root = Path(__file__).resolve().parents[3]
        for name in (
            "PHASE_24_PROVIDER_QUALIFICATION.md",
            "PHASE_24_DATA_PARITY.md",
            "PHASE_24_ARM64_COMPATIBILITY.md",
        ):
            self.assertTrue((root / "docs" / "agent" / name).is_file(), msg=name)


if __name__ == "__main__":
    unittest.main()
