"""Prompt 2 — market evidence identity regressions (retrieval-time independence)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import FakeMt5Backend
from phase66.collector import collect_fixture_cycle
from phase66.constants import ACTIVE_SYMBOL, SUPERSEDED_SYMBOL
from phase66.quality import validate_m5_bar, validate_quote
from phase66.schema import (
    IDENTITY_SCHEMA_VERSION,
    build_m5_record,
    build_quote_record,
    m5_stable_key,
    quote_stable_key,
)


class TestMarketHashIndependence(unittest.TestCase):
    def test_m5_same_hash_different_collection_times(self):
        bar = {
            "timestamp_utc": "2026-01-01T12:00:00Z",
            "open": 2649.0,
            "high": 2651.0,
            "low": 2648.5,
            "close": 2650.0,
            "tick_volume": 100,
            "spread": 25,
        }
        a = build_m5_record(
            bar=bar,
            collection_time_utc="2026-01-01T12:00:05Z",
            source_server="Exness-MT5Trial15",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
        )
        b = build_m5_record(
            bar=bar,
            collection_time_utc="2026-01-01T12:05:55Z",
            source_server="Exness-MT5Trial15",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
        )
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertEqual(a["stable_key"], b["stable_key"])
        self.assertEqual(a["body_hash"], b["body_hash"])
        self.assertNotEqual(a["collection_timestamp_utc"], b["collection_timestamp_utc"])
        self.assertEqual(a["identity_schema_version"], IDENTITY_SCHEMA_VERSION)

    def test_quote_same_identity_different_collection_times(self):
        a = build_quote_record(
            bid=2650.1,
            ask=2650.35,
            server_time_utc="2026-01-01T12:00:00Z",
            collection_time_utc="2026-01-01T12:00:01Z",
            source_server="Exness-MT5Trial15",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
            raw_payload={},
        )
        b = build_quote_record(
            bid=2650.1,
            ask=2650.35,
            server_time_utc="2026-01-01T12:00:00Z",
            collection_time_utc="2026-01-01T12:00:59Z",
            source_server="Exness-MT5Trial15",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
            raw_payload={},
        )
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertEqual(a["stable_key"], b["stable_key"])

    def test_ohlc_conflict_same_bar_timestamp(self):
        bar_a = {
            "timestamp_utc": "2026-01-01T12:00:00Z",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 10,
        }
        bar_b = {**bar_a, "close": 1.6}
        a = build_m5_record(
            bar=bar_a,
            collection_time_utc="2026-01-01T12:00:05Z",
            source_server="s",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
        )
        b = build_m5_record(
            bar=bar_b,
            collection_time_utc="2026-01-01T12:00:06Z",
            source_server="s",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
        )
        self.assertEqual(a["stable_key"], b["stable_key"])
        self.assertNotEqual(a["content_hash"], b["content_hash"])
        with tempfile.TemporaryDirectory() as td:
            j = BrokerEvidenceJournal(Path(td), allow_synthetic=True, store_label="FIXTURE")
            batch = j.begin_batch(source_file="t", source_sha256="x", parser_version="t")
            r1 = j.append_event(a, import_batch_id=batch)
            r2 = j.append_event(b, import_batch_id=batch)
            self.assertEqual(r1["status"], "INGESTED")
            self.assertEqual(r2["status"], "QUARANTINED")
            self.assertEqual(r2.get("reason"), "conflicting_broker_evidence")
            self.assertEqual(len(j.all_events()), 1)
            self.assertGreaterEqual(len(j.quarantine_rows()), 1)

    def test_different_symbols_no_collide(self):
        bar = {
            "timestamp_utc": "2026-01-01T12:00:00Z",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 1,
        }
        a = build_m5_record(
            bar=bar,
            collection_time_utc="t1",
            source_server="s",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
            symbol=ACTIVE_SYMBOL,
        )
        b = build_m5_record(
            bar=bar,
            collection_time_utc="t1",
            source_server="s",
            session_state="OPEN",
            evidence_class="SYNTHETIC_TEST_FIXTURE",
            symbol=SUPERSEDED_SYMBOL,
        )
        self.assertNotEqual(a["stable_key"], b["stable_key"])
        self.assertNotEqual(a["content_hash"], b["content_hash"])

    def test_different_timeframes_no_collide(self):
        # Quote vs M5 at same server ts must not share stable_key namespace
        q = quote_stable_key(symbol=ACTIVE_SYMBOL, server_time_utc="2026-01-01T12:00:00Z")
        m = m5_stable_key(symbol=ACTIVE_SYMBOL, server_timestamp_utc="2026-01-01T12:00:00Z")
        self.assertNotEqual(q, m)
        self.assertTrue(q.startswith("market_quote:"))
        self.assertTrue(m.startswith("market_m5:"))

    def test_fixture_idempotent_across_wall_clock_gap(self):
        with tempfile.TemporaryDirectory() as td:
            frozen = int(datetime.now(timezone.utc).timestamp()) - 10
            out = collect_fixture_cycle(
                journal_root=Path(td), rounds=2, wall_clock_gap_sec=1.1, frozen_server_unix=frozen
            )
            self.assertTrue(out["idempotent_second_round_duplicates"], msg=str(out["rounds"][-1].get("stats")))
            self.assertGreaterEqual(out["n_events"], 2)  # quote + m5
            n = out["n_events"]
            out2 = collect_fixture_cycle(
                journal_root=Path(td), rounds=1, wall_clock_gap_sec=0, frozen_server_unix=frozen
            )
            self.assertEqual(out2["n_events"], n)
            self.assertGreaterEqual(out2["rounds"][0]["stats"]["DUPLICATE_SUPPRESSED"], 1)

    def test_restart_dedupe_persists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            frozen = int(datetime.now(timezone.utc).timestamp()) - 10
            out1 = collect_fixture_cycle(journal_root=root, rounds=1, frozen_server_unix=frozen)
            self.assertGreaterEqual(out1["n_events"], 2)
            n = out1["n_events"]
            out2 = collect_fixture_cycle(journal_root=root, rounds=1, frozen_server_unix=frozen)
            self.assertGreaterEqual(out2["rounds"][0]["stats"]["DUPLICATE_SUPPRESSED"], 1)
            self.assertEqual(out2["n_events"], n)

    def test_backfill_provenance_not_reclassified_on_reread(self):
        from phase66.collector import _stamp_provenance

        bar = {
            "timestamp_utc": "2026-01-01T10:00:00Z",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 1,
        }
        rec = build_m5_record(
            bar=bar,
            collection_time_utc="2026-01-01T12:00:00Z",
            source_server="s",
            session_state="OPEN",
            evidence_class="BROKER_OBSERVED",
        )
        started = "2026-01-01T12:00:00Z"
        stamped = _stamp_provenance(
            rec,
            synthetic=False,
            kind="m5",
            collector_started_utc=started,
            collection_time_utc="2026-01-01T12:00:00Z",
            cycle=1,
        )
        self.assertEqual(stamped["evidence_provenance"], "HISTORICAL_BACKFILL")
        # Re-stamp later collection of same market bar — still backfill vs process start
        stamped2 = _stamp_provenance(
            {**rec, "collection_timestamp_utc": "2026-01-01T12:10:00Z"},
            synthetic=False,
            kind="m5",
            collector_started_utc=started,
            collection_time_utc="2026-01-01T12:10:00Z",
            cycle=2,
        )
        self.assertEqual(stamped2["evidence_provenance"], "HISTORICAL_BACKFILL")
        self.assertEqual(stamped["stable_key"], stamped2["stable_key"])

    def test_live_not_manufactured_from_lookback(self):
        # Bar that closed before process start is backfill, never live
        from phase66.collector import _stamp_provenance

        bar = {
            "timestamp_utc": "2026-01-01T11:55:00Z",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "tick_volume": 1,
        }
        rec = build_m5_record(
            bar=bar,
            collection_time_utc="2026-01-01T12:00:30Z",
            source_server="s",
            session_state="OPEN",
            evidence_class="BROKER_OBSERVED",
        )
        stamped = _stamp_provenance(
            rec,
            synthetic=False,
            kind="m5",
            collector_started_utc="2026-01-01T12:00:00Z",
            collection_time_utc="2026-01-01T12:00:30Z",
            cycle=1,
        )
        self.assertEqual(stamped["evidence_provenance"], "HISTORICAL_BACKFILL")
        self.assertNotEqual(stamped["evidence_provenance"], "BROKER_OBSERVED_LIVE_BAR")

    def test_quality_gates_still_reject_malformed(self):
        bad_q = validate_quote(
            symbol=ACTIVE_SYMBOL,
            bid=10.0,
            ask=9.0,
            server_time_utc="2026-01-01T00:00:00Z",
            collection_time_utc="2026-01-01T00:00:01Z",
        )
        self.assertEqual(bad_q["validation_status"], "REJECTED")
        bad_m = validate_m5_bar({"open": 1, "high": 2, "low": 0.5, "timestamp_utc": "2026-01-01T00:00:00Z"})
        self.assertEqual(bad_m["validation_status"], "REJECTED")

    def test_integrity_after_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            frozen = int(datetime.now(timezone.utc).timestamp()) - 10
            out = collect_fixture_cycle(
                journal_root=Path(td), rounds=3, wall_clock_gap_sec=0.05, frozen_server_unix=frozen
            )
            integ = out["journal_integrity"]
            self.assertTrue(integ.get("index_matches"))
            self.assertTrue(integ.get("append_only"))
            self.assertGreaterEqual(out["n_events"], 2)


class TestDiscrepancyReproduction(unittest.TestCase):
    """Document Prompt1 flake: wall-clock advancing FakeMt5Backend times broke old hashes.

    With frozen server times + market-only hash, gap must not break idempotency.
    """

    def test_adversarial_style_gap_still_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            frozen = int(datetime.now(timezone.utc).timestamp()) - 10
            out = collect_fixture_cycle(
                journal_root=Path(td), rounds=2, wall_clock_gap_sec=1.05, frozen_server_unix=frozen
            )
            self.assertTrue(
                out["idempotent_second_round_duplicates"],
                msg=f"stats={out['rounds'][-1].get('stats')} n_events={out['n_events']}",
            )


if __name__ == "__main__":
    unittest.main()
