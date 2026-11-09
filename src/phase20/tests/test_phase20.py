"""Deterministic Phase 20 real-shadow pipeline tests (no live market dependency)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase16b.dedupe import DeliveryLedger
from phase18.constants import HORIZONS
from phase18.experience import ExperienceStore
from phase18.outcomes import create_pending_outcomes
from phase18.store import Phase18Store
from phase19.fixtures import build_scenario
from phase20.candles import filter_completed_bars, is_complete_m5_bar
from phase20.constants import (
    BROKER_ORDERS,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    HOLDOUT_ACCESSES,
    PHASE19_SYNTHETIC,
    SELECTED_HORIZON_DISPLAY,
    SHADOW_DISCLAIMER,
    SOURCE_HISTORICAL,
    SOURCE_SHADOW,
)
from phase20.integrity import integrity_report, verify_protected_hashes
from phase20.loop import Phase20LoopError, process_bar, resolve_pending_outcomes, run_bounded_real_shadow_loop
from phase20.messages import build_shadow_signal_payload
from phase20.reporting import build_activity_summary

UTC = timezone.utc


def _bar(open_utc: str, o: float, h: float, l: float, c: float) -> dict:
    close_dt = datetime.strptime(open_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) + timedelta(minutes=5)
    return {
        "bar_open_timestamp_utc": open_utc,
        "bar_close_timestamp_utc": close_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "spread": 20.0,
        "tick_volume": 100,
        "data_source": "synthetic_fixture",
    }


class Phase20Tests(unittest.TestCase):
    def test_01_completed_candle_ingestion(self):
        bar = _bar("2026-11-09 12:00:00", 1, 2, 0.5, 1.5)
        self.assertTrue(is_complete_m5_bar(bar, as_of_utc="2026-11-09 12:05:01"))
        bars = filter_completed_bars([bar], as_of_utc="2026-11-09 12:05:01")
        self.assertEqual(len(bars), 1)

    def test_02_incomplete_candle_rejection(self):
        bar = _bar("2026-11-09 12:00:00", 1, 2, 0.5, 1.5)
        # as_of equal to close → still forming for our strict rule
        self.assertFalse(is_complete_m5_bar(bar, as_of_utc="2026-11-09 12:05:00"))
        self.assertFalse(is_complete_m5_bar(bar, as_of_utc="2026-11-09 12:04:59"))

    def test_03_duplicate_candle_rejection(self):
        fake_pred = {
            "experimental_action": "WAIT",
            "raw_action": "WAIT",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "t",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot_json": "{}",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            ledger = DeliveryLedger(root / "ledger.jsonl")
            bars = [_bar(f"2026-11-09 10:{i:02d}:00", 2000, 2001, 1999, 2000.5) for i in range(0, 50, 5)]
            # fix timestamps properly
            bars = []
            t0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
            for i in range(25):
                ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
                bars.append(_bar(ts, 2000 + i * 0.1, 2001, 1999, 2000.2))
            bar = bars[20]
            as_of = "2026-11-09 14:00:00"
            with patch("phase20.loop.predict_h13c_experimental", return_value=fake_pred):
                r1 = process_bar(
                    store=store,
                    experience=experience,
                    bar=bar,
                    closes_prefix=[float(b["close"]) for b in bars[:21]],
                    h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 30,
                    all_bars=bars,
                    as_of=as_of,
                    prev_open=bars[19]["bar_open_timestamp_utc"],
                    discord_enabled=False,
                    dry_run_discord=True,
                    ledger=ledger,
                )
                r2 = process_bar(
                    store=store,
                    experience=experience,
                    bar=bar,
                    closes_prefix=[float(b["close"]) for b in bars[:21]],
                    h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 30,
                    all_bars=bars,
                    as_of=as_of,
                    prev_open=bars[19]["bar_open_timestamp_utc"],
                    discord_enabled=False,
                    dry_run_discord=True,
                    ledger=ledger,
                )
            self.assertTrue(r1["journaled"])
            self.assertTrue(r2.get("duplicate"))
            self.assertEqual(len(store.decisions()), 1)

    def test_04_05_buy_sell_lifecycle(self):
        for kind, action in (("BUY_PASS", "BUY"), ("SELL_FAIL", "SELL")):
            scenario = build_scenario(kind)
            fake_pred = {
                "experimental_action": action,
                "raw_action": action,
                "final_action": "WAIT",
                "champion_status": CHAMPION_STATUS,
                "experimental_reason": "synthetic_for_test",
                "gate": {"gate_status": "ALLOW"},
                "feature_snapshot_json": "{}",
            }
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                store = Phase18Store(root)
                experience = ExperienceStore(root)
                ledger = DeliveryLedger(root / "ledger.jsonl")
                bars = scenario["bars"]
                idx = scenario["signal_idx"]
                bar = bars[idx]
                as_of = bars[-1]["bar_close_timestamp_utc"]
                with patch("phase20.loop.predict_h13c_experimental", return_value=fake_pred):
                    result = process_bar(
                        store=store,
                        experience=experience,
                        bar=bar,
                        closes_prefix=[float(b["close"]) for b in bars[: idx + 1]],
                        h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40,
                        all_bars=bars,
                        as_of=as_of,
                        prev_open=bars[idx - 1]["bar_open_timestamp_utc"],
                        discord_enabled=True,
                        dry_run_discord=True,
                        ledger=ledger,
                    )
                self.assertEqual(result["experimental_action"], action)
                self.assertEqual(result["final_action"], "WAIT")
                self.assertEqual(result["pending_outcomes"], 5)
                self.assertEqual(result["delivery"]["status"], "DRY_RUN")
                resolved = resolve_pending_outcomes(
                    store=store,
                    experience=experience,
                    bars=bars,
                    as_of=as_of,
                    discord_enabled=True,
                    dry_run_discord=True,
                    ledger=ledger,
                )
                self.assertGreaterEqual(len(resolved["finalized"]), 1)
                statuses = {o["status"] for o in store.outcomes()}
                self.assertTrue(statuses & {"PASS", "FAIL", "TIMEOUT"})

    def test_06_wait_no_outcome(self):
        fake_pred = {
            "experimental_action": "WAIT",
            "raw_action": "WAIT",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "wait",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot_json": "{}",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            ledger = DeliveryLedger(root / "ledger.jsonl")
            scenario = build_scenario("TIMEOUT")
            bars = scenario["bars"]
            idx = scenario["signal_idx"]
            with patch("phase20.loop.predict_h13c_experimental", return_value=fake_pred):
                result = process_bar(
                    store=store,
                    experience=experience,
                    bar=bars[idx],
                    closes_prefix=[float(b["close"]) for b in bars[: idx + 1]],
                    h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40,
                    all_bars=bars,
                    as_of=bars[-1]["bar_close_timestamp_utc"],
                    prev_open=bars[idx - 1]["bar_open_timestamp_utc"],
                    discord_enabled=True,
                    dry_run_discord=True,
                    ledger=ledger,
                )
            self.assertEqual(result["pending_outcomes"], 0)
            self.assertEqual(result["delivery"]["status"], "SKIPPED_WAIT_NO_DISCORD")
            self.assertEqual(len(store.outcomes()), 0)

    def test_07_to_10_horizons_pass_fail_timeout(self):
        self.assertEqual(len(HORIZONS), 5)
        for kind, expected in (
            ("BUY_PASS", "PASS"),
            ("BUY_FAIL", "FAIL"),
            ("TIMEOUT", "TIMEOUT"),
        ):
            scenario = build_scenario(kind)
            with tempfile.TemporaryDirectory() as tmp:
                store = Phase18Store(Path(tmp))
                experience = ExperienceStore(Path(tmp))
                ledger = DeliveryLedger(Path(tmp) / "l.jsonl")
                dec = scenario["decision"]
                # rewrite ids to p20 style but keep fields
                dec = dict(dec)
                store.append_decision(dec)
                store.append_outcomes(create_pending_outcomes(dec, atr=scenario["atr"]))
                resolved = resolve_pending_outcomes(
                    store=store,
                    experience=experience,
                    bars=scenario["bars"],
                    as_of=scenario["bars"][-1]["bar_close_timestamp_utc"],
                    discord_enabled=False,
                    dry_run_discord=True,
                    ledger=ledger,
                )
                h12 = next(o for o in store.outcomes() if o["horizon_id"] == "H12")
                self.assertEqual(h12["status"], expected, kind)
                self.assertEqual(len(store.outcomes()), 5)

    def test_11_discord_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DeliveryLedger(Path(tmp) / "l.jsonl")
            event = {"event_id": "d1", "decision_id": "d1", "message_type": "SHADOW_SIGNAL_BUY"}
            self.assertFalse(ledger.already_sent(event))
            ledger.record(event, {"status": "SENT", "attempts": 1})
            self.assertTrue(ledger.already_sent(event))

    def test_12_restart_recovery(self):
        scenario = build_scenario("SELL_PASS")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            ledger = DeliveryLedger(root / "l.jsonl")
            dec = scenario["decision"]
            store.append_decision(dec)
            store.append_outcomes(create_pending_outcomes(dec, atr=scenario["atr"]))
            self.assertEqual(len(store.pending_outcomes()), 5)
            as_of = scenario["bars"][-1]["bar_close_timestamp_utc"]
            first = resolve_pending_outcomes(
                store=store,
                experience=experience,
                bars=scenario["bars"],
                as_of=as_of,
                discord_enabled=True,
                dry_run_discord=True,
                ledger=ledger,
            )
            before = experience.counts()["agent_shadow"]
            second = resolve_pending_outcomes(
                store=store,
                experience=experience,
                bars=scenario["bars"],
                as_of=as_of,
                discord_enabled=True,
                dry_run_discord=True,
                ledger=ledger,
            )
            self.assertGreater(len(first["finalized"]), 0)
            self.assertEqual(len(second["finalized"]), 0)
            self.assertEqual(experience.counts()["agent_shadow"], before)
            self.assertEqual(len(store.pending_outcomes()), 0)

    def test_13_14_experience_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            experience = ExperienceStore(root)
            experience.add_shadow_from_outcome(
                {
                    "outcome_event_id": "real__H1",
                    "decision_id": "real",
                    "side": "BUY",
                    "status": "PASS",
                    "symbol": "XAUUSD",
                    "horizon_id": "H1",
                    "horizon_label": "5M",
                    "decision_timestamp_utc": "2026-11-09 12:00:00",
                    "realized_r": "1.0",
                    "outcome_timestamp_utc": "2026-11-09 12:05:00",
                }
            )
            experience.add_historical(
                {
                    "outcome_event_id": "hist__H12",
                    "event_id": "hist",
                    "side": "SELL",
                    "action": "SELL",
                    "outcome": "FAIL",
                    "realized_r": "-1.0",
                    "decision_timestamp_utc": "2026-01-01 10:00:00",
                    "outcome_timestamp_utc": "2026-01-01 11:00:00",
                }
            )
            self.assertEqual(experience.list_shadow()[0]["source"], SOURCE_SHADOW)
            self.assertEqual(experience.list_historical()[0]["source"], SOURCE_HISTORICAL)

    def test_15_synthetic_phase19_isolation(self):
        with self.assertRaises(Phase20LoopError):
            run_bounded_real_shadow_loop(
                max_candles=1,
                store_root=PHASE19_SYNTHETIC,
                bar_source=lambda: ([], [], "2026-11-09 12:00:00"),
                dry_run_discord=True,
            )

    def test_16_17_production_wait_and_no_orders(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(CANDIDATE_STATUS, "EXPERIMENTAL")
        self.assertEqual(BROKER_ORDERS, 0)
        self.assertEqual(SELECTED_HORIZON_DISPLAY, "NOT ESTABLISHED")
        scenario = build_scenario("BUY_PASS")
        payload = build_shadow_signal_payload(scenario["decision"], scenario["observation"])
        self.assertIn(SHADOW_DISCLAIMER, payload["content"])
        self.assertIn("Expected Horizon: NOT ESTABLISHED", payload["content"])
        self.assertIn("Production Action: WAIT", payload["content"])
        self.assertNotIn("will hit target in", payload["content"].lower())

    def test_18_holdout_and_integrity(self):
        self.assertEqual(HOLDOUT_ACCESSES, 0)
        report = verify_protected_hashes()
        self.assertTrue(report["all_ok"], msg=json.dumps({k: v for k, v in report["files"].items() if not v["ok"]}, indent=2))
        integ = integrity_report()
        self.assertFalse(integ["github_push"])
        self.assertEqual(integ["production_final_action"], "WAIT")

    def test_19_bounded_loop_offline(self):
        bars = []
        t0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
        for i in range(30):
            ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
            bars.append(_bar(ts, 2000, 2001, 1999, 2000.2))
        fake_pred = {
            "experimental_action": "WAIT",
            "raw_action": "WAIT",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "flat",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot_json": "{}",
        }

        def source():
            return bars, [{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40, "2026-11-09 14:00:00"

        with tempfile.TemporaryDirectory() as tmp:
            with patch("phase20.loop.predict_h13c_experimental", return_value=fake_pred):
                result = run_bounded_real_shadow_loop(
                    max_candles=3,
                    store_root=Path(tmp),
                    bar_source=source,
                    dry_run_discord=True,
                )
            self.assertEqual(result["candles_processed"], 3)
            self.assertEqual(result["prediction_counts"]["WAIT"], 3)
            self.assertFalse(result["any_final_non_wait"])
            self.assertEqual(result["broker_orders"], 0)
            self.assertTrue(result["phase19_synthetic_excluded"])
            summary = build_activity_summary(
                store=Phase18Store(Path(tmp)),
                experience=ExperienceStore(Path(tmp)),
                session=result,
            )
            self.assertEqual(summary["WAIT_count"], 3)
            self.assertTrue(summary["phase19_synthetic_records_excluded"])
            self.assertIn("not proof of a trading edge", summary["note"].lower())

    def test_20_hard_failure_non_wait_final(self):
        bad = {
            "experimental_action": "BUY",
            "raw_action": "BUY",
            "final_action": "BUY",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "bad",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot_json": "{}",
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = Phase18Store(Path(tmp))
            experience = ExperienceStore(Path(tmp))
            ledger = DeliveryLedger(Path(tmp) / "l.jsonl")
            scenario = build_scenario("BUY_PASS")
            bars = scenario["bars"]
            idx = scenario["signal_idx"]
            with patch("phase20.loop.predict_h13c_experimental", return_value=bad):
                with self.assertRaises(Phase20LoopError):
                    process_bar(
                        store=store,
                        experience=experience,
                        bar=bars[idx],
                        closes_prefix=[float(b["close"]) for b in bars[: idx + 1]],
                        h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40,
                        all_bars=bars,
                        as_of=bars[-1]["bar_close_timestamp_utc"],
                        prev_open=bars[idx - 1]["bar_open_timestamp_utc"],
                        discord_enabled=False,
                        dry_run_discord=True,
                        ledger=ledger,
                    )


if __name__ == "__main__":
    unittest.main()
