"""Unit tests for Phase 66 read-only market evidence collection."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import FakeMt5Backend
from phase64_13.constants import CLOSE_ONLY, OPEN
from phase64_13.schedule import state_at_utc
from phase66.adversarial import run_adversarial_tests
from phase66.collector import collect_fixture_cycle, collect_once
from phase66.constants import (
    ACTIVE_SYMBOL,
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    SUPERSEDED_SYMBOL,
    SYNTHETIC_TEST_FIXTURE,
)
from phase66.dual_experience import evaluate_dual_experience_isolation
from phase66.eligibility import build_eligibility_registry
from phase66.integrity import audit_integrity
from phase66.quality import validate_m5_bar, validate_quote
from phase66.schema import build_quote_record, stable_evidence_id, to_pkt
from phase66.security import security_audit
from phase66.spread_stats import compute_spread_stats
from phase66.watermark import load_watermark, save_watermark


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase66_market_evidence_collection_v1")

    def test_champion_wait(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)


class TestIdentityAndTimestamps(unittest.TestCase):
    def test_stable_id(self):
        a = stable_evidence_id(kind="quote", symbol=ACTIVE_SYMBOL, server_ts="t", payload_key="p")
        b = stable_evidence_id(kind="quote", symbol=ACTIVE_SYMBOL, server_ts="t", payload_key="p")
        self.assertEqual(a, b)

    def test_pkt(self):
        self.assertIn("05:00", to_pkt("2026-06-01T00:00:00Z") or "")


class TestQuality(unittest.TestCase):
    def test_bid_gt_ask(self):
        r = validate_quote(
            symbol=ACTIVE_SYMBOL,
            bid=2.0,
            ask=1.0,
            server_time_utc="2026-01-01T00:00:00Z",
            collection_time_utc="2026-01-01T00:00:01Z",
        )
        self.assertEqual(r["validation_status"], "REJECTED")

    def test_stale(self):
        r = validate_quote(
            symbol=ACTIVE_SYMBOL,
            bid=2650.0,
            ask=2650.1,
            server_time_utc="2020-01-01T00:00:00Z",
            collection_time_utc="2026-01-01T00:00:00Z",
        )
        self.assertIn("stale_observation", r["rejection_reasons"])

    def test_incomplete_candle(self):
        r = validate_m5_bar({"open": 1, "high": 2, "low": 0.5, "timestamp_utc": "2026-01-01T00:00:00Z"})
        self.assertEqual(r["validation_status"], "REJECTED")


class TestCollection(unittest.TestCase):
    def test_fixture_cycle_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            out = collect_fixture_cycle(journal_root=Path(td), rounds=2)
            self.assertEqual(out["rounds"][0]["status"], "OK")
            self.assertTrue(out["idempotent_second_round_duplicates"])
            self.assertTrue(out["synthetic_fixture_only"])

    def test_wrong_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            j = BrokerEvidenceJournal(Path(td), allow_synthetic=True, store_label="FIXTURE")
            r = collect_once(FakeMt5Backend(), j, symbol=SUPERSEDED_SYMBOL, synthetic=True, watermark_path=Path(td) / "w.json")
            self.assertEqual(r["status"], "BLOCKED")

    def test_synthetic_not_in_genuine(self):
        with tempfile.TemporaryDirectory() as td:
            j = BrokerEvidenceJournal(Path(td), allow_synthetic=False, store_label="GENUINE")
            q = build_quote_record(
                bid=2650.0,
                ask=2650.2,
                server_time_utc="2026-01-01T00:00:00Z",
                collection_time_utc="2026-01-01T00:00:01Z",
                source_server="Exness-MT5Trial15",
                session_state="OPEN",
                evidence_class=SYNTHETIC_TEST_FIXTURE,
                raw_payload={},
            )
            b = j.begin_batch(source_file="t", source_sha256="x", parser_version="t")
            self.assertEqual(j.append_event(q, import_batch_id=b)["status"], "QUARANTINED")


class TestSessionAndEligibility(unittest.TestCase):
    def test_session_states(self):
        co = state_at_utc(datetime(2026, 11, 10, 23, 1, 0, tzinfo=timezone.utc))
        op = state_at_utc(datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(co["state"], CLOSE_ONLY)
        self.assertEqual(op["state"], OPEN)

    def test_eligibility_holdout(self):
        e = build_eligibility_registry()
        self.assertFalse(e["phase58_holdout_accessed"])
        self.assertEqual(len(e["phase58_holdout_sealed"]), 10)
        self.assertFalse(e["independent_research_evidence_sufficient"])

    def test_dual_isolation(self):
        self.assertTrue(evaluate_dual_experience_isolation()["isolation_ok"])


class TestSpreadAndWatermark(unittest.TestCase):
    def test_spread_stats(self):
        quotes = [
            {
                "kind": "QUOTE_SNAPSHOT",
                "validation_status": "OK",
                "spread": 0.25,
                "session_state": "OPEN",
            },
            {
                "kind": "QUOTE_SNAPSHOT",
                "validation_status": "OK",
                "spread": 0.30,
                "session_state": "OPEN",
            },
        ]
        s = compute_spread_stats(quotes)
        self.assertEqual(s["n_observations"], 2)
        self.assertFalse(s["establishes_commission"])

    def test_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "w.json"
            save_watermark({"n_quotes": 3, "last_quote_server_ts": "t"}, p)
            self.assertEqual(load_watermark(p)["n_quotes"], 3)


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])

    def test_security(self):
        self.assertTrue(security_audit()["pass"])


if __name__ == "__main__":
    unittest.main()
