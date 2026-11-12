"""Prompt 5 — durable live evidence pipeline tests (no fabricated broker fills)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import FakeMt5Backend
from phase66.collector import collect_once
from phase66.constants import ACTIVE_SYMBOL
from phase66.schema import build_m5_record, m5_stable_key
from phase67.session_evidence import build_session_evidence_report, _session_bar_timestamps


class TestMarketIdentityDedupe(unittest.TestCase):
    def test_legacy_key_and_v2_key_dedupe_same_bar(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            j = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
            batch = j.begin_batch(source_file="t", source_sha256="a", parser_version="t")
            bar = {
                "timestamp_utc": "2026-03-10T01:00:00Z",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 10,
                "spread": 1,
            }
            # Legacy-style key (content hash suffix) already in journal
            legacy = build_m5_record(
                bar=bar,
                collection_time_utc="2026-03-10T01:10:00Z",
                source_server="Exness-MT5Trial15",
                session_state="OPEN",
                evidence_class="SYNTHETIC_TEST_FIXTURE",
            )
            legacy["stable_key"] = f"market_m5:{ACTIVE_SYMBOL}:2026-03-10T01:00:00Z:deadbeef"
            legacy["event_id"] = "evt_legacy_1"
            r1 = j.append_event(legacy, import_batch_id=batch)
            self.assertEqual(r1["status"], "INGESTED")
            # v2 key same market payload
            v2 = build_m5_record(
                bar=bar,
                collection_time_utc="2026-03-10T01:20:00Z",
                source_server="Exness-MT5Trial15",
                session_state="OPEN",
                evidence_class="SYNTHETIC_TEST_FIXTURE",
            )
            self.assertEqual(v2["stable_key"], m5_stable_key(symbol=ACTIVE_SYMBOL, server_timestamp_utc=bar["timestamp_utc"]))
            r2 = j.append_event(v2, import_batch_id=batch)
            self.assertEqual(r2["status"], "DUPLICATE_SUPPRESSED")
            self.assertEqual(r2.get("via"), "market_identity")
            self.assertEqual(len(j.all_events()), 1)

    def test_conflict_quarantine_same_identity_different_ohlc(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            j = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
            batch = j.begin_batch(source_file="t", source_sha256="a", parser_version="t")
            bar1 = {
                "timestamp_utc": "2026-03-10T01:00:00Z",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "tick_volume": 10,
            }
            bar2 = {**bar1, "close": 1.7}
            a = build_m5_record(
                bar=bar1,
                collection_time_utc="2026-03-10T01:10:00Z",
                source_server="s",
                session_state="OPEN",
                evidence_class="SYNTHETIC_TEST_FIXTURE",
            )
            b = build_m5_record(
                bar=bar2,
                collection_time_utc="2026-03-10T01:11:00Z",
                source_server="s",
                session_state="OPEN",
                evidence_class="SYNTHETIC_TEST_FIXTURE",
            )
            self.assertEqual(j.append_event(a, import_batch_id=batch)["status"], "INGESTED")
            self.assertEqual(j.append_event(b, import_batch_id=batch)["status"], "QUARANTINED")
            self.assertEqual(len(j.all_events()), 1)
            self.assertGreaterEqual(len(j.quarantine_rows()), 1)


class TestFormingBarSkip(unittest.TestCase):
    def test_forming_bar_not_journalled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            j = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
            backend = FakeMt5Backend()
            now = int(datetime.now(timezone.utc).timestamp())
            # Align to current forming M5 open
            open_unix = now - (now % 300)
            backend.symbol = {
                "name": ACTIVE_SYMBOL,
                "bid": 2650.1,
                "ask": 2650.35,
                "time": now,
                "point": 0.001,
                "trade_tick_size": 0.001,
            }
            backend.rates = [
                {
                    "time": open_unix,
                    "open": 2649.0,
                    "high": 2651.0,
                    "low": 2648.5,
                    "close": 2650.0,
                    "tick_volume": 100,
                    "spread": 25,
                    "timestamp_utc": datetime.fromtimestamp(open_unix, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
            ]
            out = collect_once(
                backend,
                j,
                synthetic=True,
                watermark_path=root / "wm.json",
                m5_count=1,
                collector_started_utc=datetime.fromtimestamp(now - 3600, tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            )
            self.assertEqual(out["status"], "OK")
            self.assertGreaterEqual(out["stats"]["FORMING_SKIPPED"], 1)
            # Only quote may ingest
            self.assertEqual(len([e for e in j.all_events() if e.get("kind") == "M5_BAR"]), 0)


class TestSessionEvidence(unittest.TestCase):
    def test_asia_london_expected_counts(self):
        asia = _session_bar_timestamps("2026-03-10", "Asia/Tokyo", (9, 0), (15, 0))
        london = _session_bar_timestamps("2026-03-10", "Europe/London", (8, 0), (12, 0))
        self.assertEqual(len(asia), 72)
        self.assertEqual(len(london), 48)

    def test_incomplete_not_qualified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # empty journal
            BrokerEvidenceJournal(root, allow_synthetic=False, store_label="GENUINE")
            rep = build_session_evidence_report(journal_root=root)
            self.assertEqual(rep["n_independent_complete_live_dates"], 0)
            self.assertFalse(rep["target_met"])


class TestDisconnectNoFabrication(unittest.TestCase):
    def test_disconnected_terminal_no_events(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            j = BrokerEvidenceJournal(root, allow_synthetic=False, store_label="GENUINE")
            backend = FakeMt5Backend()
            backend.connected = False
            out = collect_once(backend, j, synthetic=False, watermark_path=root / "wm.json", m5_count=1)
            self.assertEqual(out["status"], "BLOCKED")
            self.assertEqual(len(j.all_events()), 0)


if __name__ == "__main__":
    unittest.main()
