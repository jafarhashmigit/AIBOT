"""Prompt 2 — supervised RO collector lifecycle tests (no live broker / no Discord)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from phase64_5.journal import BrokerEvidenceJournal
from phase64_6.readonly_adapter import FakeMt5Backend
from phase66.collector import collect_once
from phase66.constants import ACTIVE_SYMBOL
from phase67.config import CollectorConfig, parse_config
from phase67 import service as svc


class TestConfig(unittest.TestCase):
    def test_rejects_tight_loop(self):
        with self.assertRaises(ValueError):
            parse_config(interval_sec=1.0)

    def test_ok_defaults(self):
        cfg = parse_config(interval_sec=30.0, m5_lookback=50)
        self.assertEqual(cfg.interval_sec, 30.0)


class TestSupervisedLifecycle(unittest.TestCase):
    def test_single_instance_blocks_second_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pid_path = root / "collector.pid"
            state_path = root / "collector_state.json"
            journal_root = root / "journal"
            journal_root.mkdir()
            service_dir = root / "service"
            service_dir.mkdir()
            pid_path.write_text("1\n", encoding="utf-8")

            with mock.patch.object(svc, "PID_PATH", pid_path), mock.patch.object(
                svc, "STATE_PATH", state_path
            ), mock.patch.object(svc, "SERVICE_DIR", service_dir), mock.patch.object(
                svc, "JOURNAL_ROOT", journal_root
            ), mock.patch.object(svc, "LOG_PATH", service_dir / "collector.log"), mock.patch.object(
                svc, "RUNTIME_MANIFEST", root / "manifest.json"
            ), mock.patch.object(svc, "_pid_alive", return_value=True):
                out = svc.run_loop(interval_sec=5.0, m5_lookback=1, max_cycles=1)
                self.assertEqual(out.get("status"), "ALREADY_RUNNING")

    def test_fixture_collect_restart_dedupe(self):
        from datetime import datetime, timezone

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            j = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
            backend = FakeMt5Backend()
            now = int(datetime.now(timezone.utc).timestamp()) - 10
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
                    "time": now - 300,
                    "open": 2649.0,
                    "high": 2651.0,
                    "low": 2648.5,
                    "close": 2650.0,
                    "tick_volume": 100,
                    "spread": 25,
                    "timestamp_utc": datetime.fromtimestamp(now - 300, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
            ]
            wm = root / "wm.json"
            r1 = collect_once(backend, j, synthetic=True, watermark_path=wm, m5_count=1, collector_started_utc="2026-01-01T00:00:00Z")
            self.assertEqual(r1["status"], "OK")
            n1 = len(j.all_events())
            # simulate restart: new journal object, same files
            j2 = BrokerEvidenceJournal(root, allow_synthetic=True, store_label="FIXTURE")
            r2 = collect_once(backend, j2, synthetic=True, watermark_path=wm, m5_count=1, collector_started_utc="2026-01-01T00:00:00Z")
            self.assertEqual(r2["stats"]["DUPLICATE_SUPPRESSED"], n1)
            self.assertEqual(len(j2.all_events()), n1)

    def test_health_includes_safety_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(svc, "JOURNAL_ROOT", root / "missing_journal"), mock.patch.object(
                svc, "PID_PATH", root / "collector.pid"
            ), mock.patch.object(svc, "STATE_PATH", root / "state.json"), mock.patch.object(
                svc, "SERVICE_DIR", root
            ), mock.patch.object(svc, "LOG_PATH", root / "log.txt"):
                h = svc.health_check()
                self.assertEqual(h["order_send"], "PROHIBITED")
                self.assertEqual(h["champion"], "NO_MODEL")
                self.assertEqual(h["symbol"], ACTIVE_SYMBOL)
                self.assertIs(h["continuous_uptime_claimed"], False)
                self.assertIs(h["authorizes_execution"], False)


if __name__ == "__main__":
    unittest.main()
