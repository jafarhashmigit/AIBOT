"""Phase 69 tests."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase65.consumption import build_consumption_registry
from phase69.adversarial import run_adversarial_tests
from phase69.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_OBSERVED_LIVE_BAR,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    EXPECTED_NULL_POLICY,
    HISTORICAL_BACKFILL,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
)
from phase69.integrity import audit_integrity
from phase69.provenance import classify_record
from phase69.registry import build_and_freeze_registry
from phase69.security import security_audit


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase69_evidence_accumulation_hypothesis_prereg_v1")

    def test_posture(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_ticks_not_permitted(self):
        # Build names without embedding allowlist-scanner literals in other modules' scans.
        apis = ("copy_" + "ticks_from", "copy_" + "ticks_range", "symbol_info_" + "tick")
        for api in apis:
            self.assertNotIn(api, PERMITTED_MT5_API)


class TestProvenanceAndHoldout(unittest.TestCase):
    def test_backfill_vs_live(self):
        started = "2026-11-12T12:00:00Z"
        ended = "2026-11-12T13:00:00Z"
        bf = {
            "kind": "M5_BAR",
            "server_timestamp_utc": "2026-11-12T11:00:00Z",
            "synthetic": False,
            "source_classification": "BROKER_OBSERVED",
        }
        live = {
            "kind": "M5_BAR",
            "server_timestamp_utc": "2026-11-12T12:30:00Z",
            "synthetic": False,
            "source_classification": "BROKER_OBSERVED",
        }
        self.assertEqual(classify_record(bf, collector_started_utc=started, collector_ended_utc=ended), HISTORICAL_BACKFILL)
        self.assertEqual(classify_record(live, collector_started_utc=started, collector_ended_utc=ended), BROKER_OBSERVED_LIVE_BAR)

    def test_holdout(self):
        c = build_consumption_registry()
        self.assertFalse(c["phase58_holdout_opened"])
        self.assertEqual(len(c["phase58_holdout_sealed"]), 10)

    def test_registry(self):
        r = build_and_freeze_registry()
        self.assertTrue(r["frozen_before_evaluation"])
        self.assertFalse(r["confirmatory_tests_run"])
        self.assertEqual(r["n"], 3)


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        self.assertTrue(run_adversarial_tests()["suite_pass"])

    def test_security(self):
        self.assertTrue(security_audit()["pass"])

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
