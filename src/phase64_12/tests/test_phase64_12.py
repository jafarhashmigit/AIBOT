"""Unit tests for Phase 64.12 session evidence."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_12.adversarial import run_adversarial_tests
from phase64_12.applicability import build_applicability_matrix
from phase64_12.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    OPEN,
    ORDER_SEND,
    PHASE65,
    RECIPE_ID,
    UNKNOWN,
)
from phase64_12.freshness import freshness_policy
from phase64_12.integrity import audit_integrity
from phase64_12.journal_ingest import ingest_session_evidence
from phase64_12.schedule import state_at_utc, us_dst_season
from phase64_12.session_model import build_session_model, session_aware_preflight
from phase64_12.sources import official_source_inventory


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_12_xauusdm_session_evidence_v1")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")

    def test_invariants(self):
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(PHASE65, "NOT_STARTED")

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)


class TestSourcesAndApplicability(unittest.TestCase):
    def test_official_sources(self):
        inv = official_source_inventory()
        self.assertFalse(inv["third_party_used"])
        self.assertGreaterEqual(inv["n_sources"], 4)

    def test_applicability(self):
        a = build_applicability_matrix()
        self.assertTrue(a["applicability_justified"])
        self.assertEqual(a["target_symbol"], "XAUUSDm")
        self.assertEqual(a["published_hour_instrument"], "XAUUSD")


class TestSchedule(unittest.TestCase):
    def test_weekday_open(self):
        r = state_at_utc(datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(r["state"], OPEN)

    def test_weekend_closed(self):
        r = state_at_utc(datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(r["state"], "CLOSED")

    def test_dst_seasons(self):
        self.assertEqual(us_dst_season(date(2026, 11, 2)), "WINTER")
        self.assertEqual(us_dst_season(date(2026, 7, 1)), "SUMMER")

    def test_naive_rejected(self):
        r = state_at_utc(datetime(2026, 11, 10, 12, 0, 0))
        self.assertEqual(r["state"], UNKNOWN)

    def test_pkt(self):
        r = state_at_utc(datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc))
        self.assertIn("+05:00", r["pkt"])


class TestModelAndJournal(unittest.TestCase):
    def test_verified_model(self):
        m = build_session_model()
        self.assertTrue(m["verified"])
        self.assertFalse(m["authorizes_execution"])

    def test_missing_fail_closed(self):
        m = build_session_model(missing_schedule=True)
        pf = session_aware_preflight(now_utc=datetime(2026, 11, 10, 12, tzinfo=timezone.utc), model=m)
        self.assertTrue(pf["reject"])

    def test_freshness(self):
        f = freshness_policy()
        self.assertTrue(f["usable"])

    def test_journal_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            r = ingest_session_evidence(Path(td))
            self.assertTrue(r["all_duplicate_on_replay"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])


if __name__ == "__main__":
    unittest.main()
