"""Phase 15A offline tests. Synthetic fixtures only. No Telegram scrape. No holdout. No MT5."""

from __future__ import annotations

import sys
import unittest

from phase15a.access_options import access_feasibility_report, authorized_acquisition_options
from phase15a.backtest_design import backtest_design
from phase15a.boundaries import assert_boundaries, integration_boundaries
from phase15a.constants import (
    BUY_SELL_ENABLED,
    CHAMPION,
    CHAMPION_STATUS,
    FORBIDDEN_MERGE_SOURCES,
    HOLDOUT_NAME,
    PROVIDERS,
    SOURCE_TYPE,
    STAGE_B_AUTHORIZED,
    TELEGRAM_MESSAGES_STORED,
    TELEGRAM_SCRAPE_ATTEMPTS,
)
from phase15a.integrity import holdout_access_count, integrity_report, verify_protected_hashes
from phase15a.permission_requirements import permission_requirements_report
from phase15a.provider_inventory import build_provider_inventory, inventory_summary
from phase15a.run_phase15a import overall_conclusion, run
from phase15a.schema import (
    REQUIRED_FIELDS,
    synthetic_signal_fixtures,
    validate_signal_record,
)
from phase15a.telegram_compliance import (
    telegram_compliance_findings,
    written_permission_must_cover,
)


class Phase15ATests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_01_champion_remains_no_model(self):
        self.assertEqual(CHAMPION, "no_model")
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertFalse(BUY_SELL_ENABLED)
        self.assertFalse(STAGE_B_AUTHORIZED)

    def test_02_five_providers_inventoried(self):
        inv = build_provider_inventory()
        self.assertEqual(len(inv), 5)
        self.assertEqual(len(PROVIDERS), 5)
        ids = {r["provider_id"] for r in inv}
        self.assertEqual(
            ids,
            {
                "vasilytrader",
                "anabelsignals",
                "goldtradersunny",
                "fxpremiere",
                "unitedkings",
            },
        )

    def test_03_no_authorized_path_and_no_messages(self):
        inv = build_provider_inventory()
        summary = inventory_summary(inv)
        self.assertFalse(summary["authorized_research_path_identified"])
        self.assertFalse(summary["any_messages_collected"])
        self.assertFalse(summary["historical_coverage_verified"])
        for row in inv:
            self.assertEqual(row["messages_collected"], 0)
            self.assertFalse(row["historical_coverage_claimed"])
            self.assertIn(
                row["phase15a_outcome"],
                {
                    "PERMISSION_REQUIRED",
                    "INSUFFICIENT_ACCESS",
                    "AUTHORIZED_RESEARCH_PATH_IDENTIFIED",
                    "REJECTED",
                },
            )

    def test_04_telegram_compliance_forbids_scrape_default(self):
        findings = telegram_compliance_findings()
        self.assertEqual(findings["scraping_default"], "FORBIDDEN")
        self.assertEqual(findings["default_legal_posture"], "PERMISSION_REQUIRED")
        self.assertEqual(findings["ai_ml_use_default"], "FORBIDDEN_WITHOUT_EXPLICIT_CONSENT")
        self.assertEqual(len(findings["sources_reviewed"]), 4)
        topics = {t["topic"] for t in written_permission_must_cover()}
        self.assertIn("historical_message_access", topics)
        self.assertIn("ai_ml_use", topics)

    def test_05_access_options_a_through_d_not_implemented(self):
        options = authorized_acquisition_options()
        self.assertEqual([o["option_id"] for o in options], ["A", "B", "C", "D"])
        for o in options:
            self.assertFalse(o["implement_now"])
        report = access_feasibility_report()
        self.assertFalse(report["any_option_authorized_now"])
        self.assertFalse(report["scraping_allowed"])
        self.assertFalse(report["bot_api_historical_harvest_allowed"])
        self.assertFalse(report["acquisition_mechanism_implemented"])

    def test_06_synthetic_schema_validates(self):
        fixtures = synthetic_signal_fixtures()
        self.assertGreaterEqual(len(fixtures), 6)
        for fix in fixtures:
            errs = validate_signal_record(fix)
            self.assertEqual(errs, [], msg=f"{fix['signal_id']}: {errs}")
            for field in REQUIRED_FIELDS:
                self.assertIn(field, fix)
        # Must include key status cases
        statuses = {f["status"] for f in fixtures}
        for needed in ("OPEN", "MODIFIED", "CANCELLED", "AMBIGUOUS", "UNFILLED", "INCOMPLETE"):
            self.assertIn(needed, statuses)
        directions = {f["direction"] for f in fixtures}
        self.assertIn("BUY", directions)
        self.assertIn("SELL", directions)

    def test_07_no_real_provider_ids_in_fixtures(self):
        real_ids = {p["provider_id"] for p in PROVIDERS}
        for fix in synthetic_signal_fixtures():
            self.assertNotIn(fix["provider_id"], real_ids)
            self.assertEqual(fix["data_provenance"], "SYNTHETIC_FIXTURE")

    def test_08_backtest_design_not_executed(self):
        design = backtest_design()
        self.assertFalse(design["executed"])
        self.assertFalse(design["profitability_calculated"])
        self.assertFalse(design["uses_real_telegram_messages"])
        self.assertEqual(design["eligibility"]["earliest_entry_rule"], "published_at_utc")
        self.assertEqual(design["exit_model"]["same_candle_sl_tp"], "CONSERVATIVE_ADVERSE — assume SL hit before TP when both possible in one bar.")
        self.assertIn("NOT_FILLED", design["outcomes"]["unfilled_status"])
        self.assertTrue(design["reporting"]["per_provider_only"])
        self.assertFalse(design["execution_gate"]["phase15a_allowed_to_execute"])

    def test_09_integration_boundaries(self):
        assert_boundaries()
        bounds = integration_boundaries()
        self.assertEqual(bounds["external_source_type"], SOURCE_TYPE)
        for src in FORBIDDEN_MERGE_SOURCES:
            self.assertIn(src, bounds["must_remain_separate_from"])
        self.assertTrue(bounds["phase6_unchanged"])
        self.assertTrue(bounds["phase12_unchanged"])
        self.assertTrue(bounds["phase12c_unchanged"])
        self.assertFalse(bounds["champion_altered"])

    def test_10_permission_requirements_none_granted(self):
        report = permission_requirements_report()
        self.assertFalse(report["any_provider_authorized"])
        for p in report["providers"]:
            self.assertFalse(p["written_permission_on_file"])
            self.assertFalse(p["ai_ml_consent_on_file"])

    def test_11_integrity_counters_zero(self):
        self.assertEqual(TELEGRAM_SCRAPE_ATTEMPTS, 0)
        self.assertEqual(TELEGRAM_MESSAGES_STORED, 0)
        self.assertEqual(holdout_access_count(), 0)
        integrity = integrity_report()
        self.assertEqual(integrity["holdout_access_count"], 0)
        self.assertEqual(integrity["mt5_connection_count"], 0)
        self.assertEqual(integrity["broker_order_count"], 0)
        self.assertFalse(integrity["real_telegram_dataset_created"])
        self.assertFalse(integrity["github_push"])
        self.assertFalse(integrity["phase15b_started"])
        protected = verify_protected_hashes()
        self.assertTrue(protected["all_ok"], msg=str(protected))

    def test_12_holdout_name_not_opened(self):
        self.assertEqual(HOLDOUT_NAME, "xauusd_m5_test.csv")
        self.assertEqual(holdout_access_count(), 0)
        # Phase 15A modules must not import or open the holdout path for reading.
        from phase15a.constants import SRC_DIR

        holdout_path = SRC_DIR / "data" / HOLDOUT_NAME
        self.assertTrue(str(holdout_path).endswith(HOLDOUT_NAME))
        self.assertEqual(holdout_access_count(), 0)

    def test_13_overall_conclusion_permission_required(self):
        inv = build_provider_inventory()
        self.assertEqual(overall_conclusion(inv), "PERMISSION_REQUIRED")

    def test_14_runner_writes_reports_and_stops(self):
        summary = run()
        self.assertEqual(summary["conclusion"], "PERMISSION_REQUIRED")
        self.assertTrue(summary["stop_at_feasibility_and_schema"])
        self.assertFalse(summary["permission_established"])
        self.assertFalse(summary["backtest_executed"])
        self.assertEqual(summary["champion_status"], "NO_MODEL")
        self.assertTrue(summary["integrity"]["phase14_hashes_ok"])
        self.assertEqual(summary["integrity"]["holdout_access_count"], 0)
        self.assertEqual(summary["integrity"]["mt5_connection_count"], 0)
        self.assertEqual(summary["integrity"]["broker_order_count"], 0)
        # Spot-check required report files exist
        from phase15a.constants import REPORTS_DIR

        for name in (
            "provider_inventory.json",
            "access_feasibility.json",
            "permission_requirements.json",
            "backtest_design.json",
            "integrity.json",
            "phase15a_summary.json",
        ):
            self.assertTrue((REPORTS_DIR / name).is_file(), msg=name)


if __name__ == "__main__":
    unittest.main()
