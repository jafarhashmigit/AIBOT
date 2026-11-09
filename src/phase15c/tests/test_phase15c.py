"""Phase 15C tests — permission registry, enforcement, import readiness."""

from __future__ import annotations

import sys
import unittest

from phase15c.constants import (
    BUY_SELL_ENABLED,
    CHAMPION,
    CHAMPION_STATUS,
    MODEL_TRAINING_RUNS,
    PERMISSION_STATUSES,
    PROVIDER_MESSAGES_SENT,
    PROVIDERS,
    TELEGRAM_CONNECTIONS,
)
from phase15c.enforcement import assert_scope_independence, evaluate_permission, run_enforcement_suite
from phase15c.import_validation import synthetic_export_fixtures, validate_all_synthetic_exports, validate_export
from phase15c.integrity import holdout_access_count, integrity_report, verify_protected_hashes
from phase15c.isolation import assert_isolation
from phase15c.registry import apply_synthetic_scenarios, build_default_registry, provider_statuses
from phase15c.run_phase15c import run
from phase15c.templates import all_request_templates


class Phase15CTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_01_champion_and_isolation(self):
        self.assertEqual(CHAMPION, "no_model")
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertFalse(BUY_SELL_ENABLED)
        self.assertEqual(MODEL_TRAINING_RUNS, 0)
        assert_isolation()

    def test_02_registry_five_providers_not_requested(self):
        reg = build_default_registry()
        self.assertEqual(len(reg["providers"]), 5)
        self.assertEqual(len(PROVIDERS), 5)
        statuses = provider_statuses(reg)
        self.assertEqual(set(statuses.values()), {"NOT_REQUESTED"})
        self.assertFalse(reg["any_provider_granted"])
        self.assertTrue(reg["inference_from_public_channel_forbidden"])
        for status in PERMISSION_STATUSES:
            self.assertIn(status, reg["allowed_statuses"])

    def test_03_templates_not_sent(self):
        templates = all_request_templates()
        self.assertFalse(templates["templates_sent"])
        self.assertFalse(templates["provider_contact_attempted"])
        self.assertEqual(len(templates["templates"]), 5)
        self.assertEqual(PROVIDER_MESSAGES_SENT, 0)
        self.assertEqual(TELEGRAM_CONNECTIONS, 0)
        for t in templates["templates"]:
            self.assertFalse(t["sent"])
            asks = " ".join(t["explicit_asks"]).lower()
            self.assertIn("historical", asks)
            self.assertIn("store", asks)
            self.assertIn("performance evaluation", asks)
            self.assertIn("retention", asks)
            self.assertIn("ai/ml", asks)

    def test_04_fail_closed_no_evidence_expired_revoked(self):
        no_ev = evaluate_permission(
            provider_id="x",
            required_scope="signal_storage",
            scope_status={"signal_storage": "GRANTED"},
            permission_evidence_reference=None,
            permission_expiry_utc="2099-01-01T00:00:00Z",
        )
        self.assertEqual(no_ev["decision"], "REJECT")
        self.assertIn("no_permission_evidence", no_ev["reasons"])

        expired = evaluate_permission(
            provider_id="x",
            required_scope="backtesting_evaluation",
            scope_status={"backtesting_evaluation": "GRANTED"},
            permission_evidence_reference="E1",
            permission_expiry_utc="2020-01-01T00:00:00Z",
        )
        self.assertEqual(expired["decision"], "REJECT")
        self.assertIn("permission_expired", expired["reasons"])

        revoked = evaluate_permission(
            provider_id="x",
            required_scope="ai_ml_training",
            scope_status={"ai_ml_training": "REVOKED"},
            permission_evidence_reference="E1",
            permission_expiry_utc="2099-01-01T00:00:00Z",
        )
        self.assertEqual(revoked["decision"], "REJECT")
        self.assertIn("permission_revoked", revoked["reasons"])

    def test_05_scope_independence_and_cross_provider(self):
        cases = {c["name"]: c["result"] for c in assert_scope_independence()}
        self.assertEqual(cases["storage_allowed_when_granted"]["decision"], "ALLOW")
        self.assertEqual(cases["backtest_rejected_without_explicit_grant"]["decision"], "REJECT")
        self.assertEqual(cases["ai_ml_rejected_even_if_backtest_granted"]["decision"], "REJECT")
        self.assertEqual(cases["cross_provider_rejected"]["decision"], "REJECT")

    def test_06_enforcement_suite_scenarios(self):
        reg = apply_synthetic_scenarios()
        suite = run_enforcement_suite(reg["synthetic_enforcement_scenarios"])
        self.assertTrue(suite["fail_closed"])
        by_name = {r["scenario"]: r for r in suite["scenario_results"]}
        self.assertEqual(
            by_name["no_evidence"]["checks"]["signal_storage"]["decision"], "REJECT"
        )
        self.assertEqual(
            by_name["storage_only"]["checks"]["backtesting_evaluation"]["decision"], "REJECT"
        )
        self.assertEqual(
            by_name["storage_only"]["checks"]["ai_ml_training"]["decision"], "REJECT"
        )
        self.assertEqual(
            by_name["backtest_without_ai"]["checks"]["backtesting_evaluation"]["decision"],
            "ALLOW",
        )
        self.assertEqual(
            by_name["backtest_without_ai"]["checks"]["ai_ml_training"]["decision"], "REJECT"
        )
        self.assertEqual(
            by_name["expired"]["checks"]["signal_storage"]["decision"], "REJECT"
        )
        self.assertEqual(
            by_name["revoked"]["checks"]["signal_storage"]["decision"], "REJECT"
        )

    def test_07_import_validation_accept_and_reject(self):
        report = validate_all_synthetic_exports()
        self.assertEqual(report["export_count"], 6)
        self.assertEqual(report["accepted_count"], 1)
        self.assertEqual(report["rejected_count"], 5)
        by_tag = {r["fixture_tag"]: r for r in report["results"]}
        self.assertTrue(by_tag["authorized_valid"]["accepted"])
        self.assertFalse(by_tag["unauthorized_no_evidence"]["accepted"])
        self.assertFalse(by_tag["integrity_mismatch"]["accepted"])
        self.assertFalse(by_tag["duplicate_ids"]["accepted"])
        self.assertFalse(by_tag["wrong_schema_version"]["accepted"])
        self.assertFalse(by_tag["cross_provider_mismatch"]["accepted"])

    def test_08_synthetic_exports_only(self):
        for exp in synthetic_export_fixtures():
            self.assertTrue(str(exp["provider_id"]).startswith("synthetic_"))
            for rec in exp["records"]:
                self.assertTrue(str(rec["signal_id"]).startswith("SYN-"))

    def test_09_integrity_protected_hashes(self):
        self.assertEqual(holdout_access_count(), 0)
        protected = verify_protected_hashes()
        self.assertTrue(protected["all_ok"], msg=str(protected))
        integrity = integrity_report()
        self.assertFalse(integrity["github_push"])
        self.assertFalse(integrity["phase1_to_15b_modified"])
        self.assertEqual(integrity["mt5_connection_count"], 0)
        self.assertEqual(integrity["broker_order_count"], 0)

    def test_10_runner_outputs(self):
        summary = run()
        self.assertEqual(summary["conclusion"], "PERMISSION_READINESS_LAYER_READY")
        self.assertEqual(summary["champion_status"], "NO_MODEL")
        self.assertTrue(summary["stop_after_phase15c"])
        self.assertFalse(summary["any_live_permission_granted"])
        self.assertFalse(summary["templates_sent"])
        self.assertTrue(summary["integrity"]["protected_hashes_ok"])
        from phase15c.constants import REPORTS_DIR

        for name in (
            "permission_registry.json",
            "import_validation.json",
            "integrity.json",
            "phase15c_summary.json",
        ):
            self.assertTrue((REPORTS_DIR / name).is_file(), msg=name)


if __name__ == "__main__":
    unittest.main()
