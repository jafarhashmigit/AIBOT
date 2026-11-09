"""Phase 15B tests — synthetic schema compatibility only."""

from __future__ import annotations

import sys
import unittest

from phase15a.schema import SCHEMA_VERSION, validate_signal_record
from phase15b.compatibility import compatibility_report
from phase15b.constants import (
    BACKTESTS_EXECUTED,
    BUY_SELL_ENABLED,
    CHAMPION,
    CHAMPION_STATUS,
    MODEL_TRAINING_RUNS,
    REAL_PROVIDER_MESSAGES_STORED,
    TARGET_SCHEMA,
    TELEGRAM_ACCESS_ATTEMPTS,
)
from phase15b.fixtures import (
    anabelsignals_style_fixtures,
    all_raw_fixtures,
    vasilytrader_style_fixtures,
)
from phase15b.integrity import holdout_access_count, integrity_report, verify_protected_hashes
from phase15b.mappers import (
    map_all_fixtures,
    map_anabelsignals_style,
    map_vasilytrader_style,
    validate_mapped,
)
from phase15b.run_phase15b import run


class Phase15BTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_01_champion_no_model(self):
        self.assertEqual(CHAMPION, "no_model")
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertFalse(BUY_SELL_ENABLED)
        self.assertEqual(TARGET_SCHEMA, SCHEMA_VERSION)
        self.assertEqual(TARGET_SCHEMA, "phase15a_signal_schema_v1")

    def test_02_synthetic_only_no_telegram(self):
        self.assertEqual(TELEGRAM_ACCESS_ATTEMPTS, 0)
        self.assertEqual(REAL_PROVIDER_MESSAGES_STORED, 0)
        for raw in all_raw_fixtures():
            self.assertIn(raw["format_style"], ("vasilytrader_style", "anabelsignals_style"))
            self.assertTrue(str(raw["fixture_id"]).startswith(("VT-", "AN-")))

    def test_03_vasily_maps_buy_sell_cancel_incomplete(self):
        mapped = [map_vasilytrader_style(r) for r in vasilytrader_style_fixtures()]
        statuses = {m["status"] for m in mapped}
        directions = {m["direction"] for m in mapped}
        self.assertIn("BUY", directions)
        self.assertIn("SELL", directions)
        self.assertIn("CANCELLED", statuses)
        self.assertIn("INCOMPLETE", statuses)
        self.assertIn("MODIFIED", statuses)
        for m in mapped:
            self.assertEqual(m["data_provenance"], "SYNTHETIC_FIXTURE")
            self.assertTrue(m["published_at_utc"].endswith("Z"))
            self.assertEqual(validate_signal_record(m), [])

    def test_04_anabel_maps_multi_tp_and_updates(self):
        records = []
        for raw in anabelsignals_style_fixtures():
            records.extend(map_anabelsignals_style(raw))
        multi = [r for r in records if len(r["take_profit_levels"]) > 1]
        self.assertGreaterEqual(len(multi), 2)
        self.assertTrue(any(r["status"] == "MODIFIED" for r in records))
        self.assertTrue(any(r["status"] == "CANCELLED" for r in records))
        self.assertTrue(any(r["status"] == "INCOMPLETE" for r in records))
        self.assertTrue(any(r["entry_type"] == "LIMIT_ZONE" for r in records))
        # Update children preserve original publication time
        child = next(r for r in records if r["signal_id"].endswith("-U1"))
        parent_id = child["update_reference"]["parent_signal_id"]
        parent = next(r for r in records if r["signal_id"] == parent_id)
        self.assertEqual(child["published_at_utc"], parent["published_at_utc"])
        self.assertNotEqual(child["last_updated_at_utc"], child["published_at_utc"])

    def test_05_all_mapped_validate_against_schema_v1(self):
        result = validate_mapped()
        self.assertTrue(result["all_ok"], msg=str(result))
        self.assertGreaterEqual(result["count"], 10)

    def test_06_compatibility_verdict(self):
        report = compatibility_report()
        self.assertEqual(report["compatibility_verdict"], "COMPATIBLE_WITH_INJECTION")
        self.assertFalse(report["real_provider_content_used"])
        self.assertFalse(report["telegram_accessed"])
        self.assertTrue(report["multiple_tp_exercised"])
        self.assertTrue(report["modified_sl_exercised"])
        self.assertTrue(report["cancellation_exercised"])
        self.assertTrue(report["incomplete_exercised"])
        missing = report["missing_ambiguous_optional"]
        self.assertIn("permission_reference", " ".join(missing["vasilytrader_style"]["missing_in_source"]))
        self.assertTrue(missing["provenance_and_timestamps"]["published_at_utc_preserved"])

    def test_07_no_backtest_or_training(self):
        self.assertEqual(BACKTESTS_EXECUTED, 0)
        self.assertEqual(MODEL_TRAINING_RUNS, 0)

    def test_08_integrity_and_protected_hashes(self):
        self.assertEqual(holdout_access_count(), 0)
        protected = verify_protected_hashes()
        self.assertTrue(protected["all_ok"], msg=str(protected))
        # Ensure Phase 15A schema hash is in the protected set
        self.assertIn("src/phase15a/schema.py", protected["files"])
        integrity = integrity_report()
        self.assertFalse(integrity["github_push"])
        self.assertFalse(integrity["phase15a_files_modified"])

    def test_09_runner_writes_reports(self):
        summary = run()
        self.assertEqual(summary["conclusion"], "COMPATIBLE_WITH_INJECTION")
        self.assertEqual(summary["champion_status"], "NO_MODEL")
        self.assertTrue(summary["stop_after_audit"])
        self.assertFalse(summary["backtest_executed"])
        self.assertTrue(summary["integrity"]["protected_hashes_ok"])
        from phase15b.constants import REPORTS_DIR

        for name in (
            "schema_compatibility.json",
            "field_mapping.json",
            "synthetic_fixtures.json",
            "mapped_signals_synthetic.json",
            "integrity.json",
            "phase15b_summary.json",
        ):
            self.assertTrue((REPORTS_DIR / name).is_file(), msg=name)

    def test_10_mapped_not_real_provider_ids(self):
        for rec in map_all_fixtures():
            self.assertIn(rec["provider_id"], ("synthetic_vasily_style", "synthetic_anabel_style"))


if __name__ == "__main__":
    unittest.main()
