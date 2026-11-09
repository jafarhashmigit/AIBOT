"""Deterministic Phase 22 campaign tests (no live MT5 dependency)."""

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
from phase18.experience import ExperienceStore
from phase18.store import Phase18Store
from phase19.fixtures import build_scenario
from phase20.candles import is_complete_m5_bar
from phase22.campaign import CampaignStore
from phase22.constants import (
    BROKER_ORDERS,
    CAMPAIGN_TARGET_CANDLES,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    FROZEN_WF3_CUTS,
    HOLDOUT_ACCESSES,
    PHASE20_DATA,
    PHASE21_HISTORICAL_BUY_RATE,
)
from phase22.diagnostics import DiagnosticJournal, build_condition_diagnostics
from phase22.integrity import frozen_thresholds_intact, integrity_report, verify_protected_hashes
from phase22.loop import Phase22LoopError, process_bar, run_bounded_campaign_session
from phase22.reporting import build_campaign_report
from phase16a.constants import FROZEN_CUTS

UTC = timezone.utc


def _bar(open_utc: str, o: float = 2000.0, h: float = 2001.0, l: float = 1999.0, c: float = 2000.2) -> dict:
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


def _bars(n: int = 30) -> list[dict]:
    t0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    out = []
    for i in range(n):
        ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
        out.append(_bar(ts, 2000 + i * 0.01, 2001, 1999, 2000.2))
    return out


class Phase22Tests(unittest.TestCase):
    def test_01_campaign_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CampaignStore(Path(tmp))
            s1 = store.get_or_create(target=1000)
            s2 = store.get_or_create(target=1000)
            self.assertEqual(s1["campaign_id"], s2["campaign_id"])
            self.assertEqual(s1["target_candles"], CAMPAIGN_TARGET_CANDLES)
            self.assertEqual(s1["observed_candles"], 0)

    def test_02_03_candle_guards(self):
        bar = _bar("2026-11-09 12:00:00")
        self.assertTrue(is_complete_m5_bar(bar, as_of_utc="2026-11-09 12:05:01"))
        self.assertFalse(is_complete_m5_bar(bar, as_of_utc="2026-11-09 12:05:00"))

    def test_04_duplicate_candle(self):
        fake = {
            "experimental_action": "WAIT",
            "raw_action": "WAIT",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "h1_up_pullback_not_met",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot": {"close_to_ema_20": 0.001, "ema_9_20_spread": 0.0005},
            "feature_snapshot_json": "{}",
            "h1_context": {"h1_trend": "up"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            ledger = DeliveryLedger(root / "l.jsonl")
            diag = DiagnosticJournal(root)
            bars = _bars(25)
            bar = bars[20]
            as_of = "2026-11-09 14:00:00"
            with patch("phase22.loop.predict_h13c_experimental", return_value=fake):
                r1 = process_bar(
                    store=store,
                    experience=experience,
                    bar=bar,
                    closes_prefix=[float(b["close"]) for b in bars[:21]],
                    h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40,
                    all_bars=bars,
                    as_of=as_of,
                    prev_open=bars[19]["bar_open_timestamp_utc"],
                    discord_enabled=False,
                    dry_run_discord=True,
                    ledger=ledger,
                    diagnostics=diag,
                    campaign_id="c1",
                    session_id="s1",
                )
                r2 = process_bar(
                    store=store,
                    experience=experience,
                    bar=bar,
                    closes_prefix=[float(b["close"]) for b in bars[:21]],
                    h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40,
                    all_bars=bars,
                    as_of=as_of,
                    prev_open=bars[19]["bar_open_timestamp_utc"],
                    discord_enabled=False,
                    dry_run_discord=True,
                    ledger=ledger,
                    diagnostics=diag,
                    campaign_id="c1",
                    session_id="s1",
                )
            self.assertTrue(r1["journaled"])
            self.assertTrue(r2["duplicate"])
            self.assertEqual(len(store.decisions()), 1)

    def test_05_buy_sell_wait_diagnostics(self):
        pred_buy = {
            "experimental_action": "BUY",
            "feature_snapshot": {
                "close_to_ema_20": FROZEN_WF3_CUTS["close_ema_low"] - 1e-6,
                "ema_9_20_spread": 0.001,
            },
            "h1_context": {"h1_trend": "up"},
        }
        d = build_condition_diagnostics(pred_buy)
        self.assertTrue(d["buy_condition"])
        self.assertFalse(d["sell_condition"])
        pred_wait = {
            "experimental_action": "WAIT",
            "feature_snapshot": {"close_to_ema_20": 0.001, "ema_9_20_spread": 0.0005},
            "h1_context": {"h1_trend": "up"},
        }
        d2 = build_condition_diagnostics(pred_wait)
        self.assertFalse(d2["buy_condition"])

    def test_06_frozen_threshold_integrity(self):
        self.assertTrue(frozen_thresholds_intact())
        self.assertEqual(FROZEN_WF3_CUTS["close_ema_low"], FROZEN_CUTS["close_ema_low"])
        self.assertEqual(FROZEN_CUTS["q_low"], 25)

    def test_07_five_horizon_tracking(self):
        scenario = build_scenario("BUY_PASS")
        fake = {
            "experimental_action": "BUY",
            "raw_action": "BUY",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "selected",
            "gate": {"gate_status": "BLOCK"},
            "feature_snapshot": scenario["decision"].get("feature_snapshot")
            or {"close_to_ema_20": FROZEN_WF3_CUTS["close_ema_low"] - 1e-4, "ema_9_20_spread": 0.001},
            "feature_snapshot_json": "{}",
            "h1_context": {"h1_trend": "up"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            ledger = DeliveryLedger(root / "l.jsonl")
            diag = DiagnosticJournal(root)
            bars = scenario["bars"]
            idx = scenario["signal_idx"]
            with patch("phase22.loop.predict_h13c_experimental", return_value=fake):
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
                    diagnostics=diag,
                    campaign_id="c1",
                    session_id="s1",
                )
            self.assertEqual(result["pending_outcomes"], 5)
            self.assertEqual(result["final_action"], "WAIT")

    def test_08_09_restart_and_progress(self):
        bars = _bars(40)
        fake = {
            "experimental_action": "WAIT",
            "raw_action": "WAIT",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "h1_up_pullback_not_met",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot": {"close_to_ema_20": 0.001, "ema_9_20_spread": 0.0005},
            "feature_snapshot_json": "{}",
            "h1_context": {"h1_trend": "up"},
        }

        def source():
            return bars, [{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40, "2026-11-09 14:00:00"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("phase22.loop.predict_h13c_experimental", return_value=fake):
                r1 = run_bounded_campaign_session(
                    max_candles=3,
                    store_root=root,
                    bar_source=source,
                    dry_run_discord=True,
                    campaign_target=10,
                )
                r2 = run_bounded_campaign_session(
                    max_candles=3,
                    store_root=root,
                    bar_source=source,
                    dry_run_discord=True,
                    campaign_target=10,
                )
            self.assertEqual(r1["candles_processed"], 3)
            self.assertEqual(r2["candles_processed"], 0)  # no newer candles
            camp = CampaignStore(root).load()
            self.assertEqual(camp["observed_candles"], 3)
            self.assertEqual(camp["campaign_id"], r1["campaign_id"])
            self.assertEqual(len(camp["sessions"]), 2)

    def test_10_discord_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DeliveryLedger(Path(tmp) / "l.jsonl")
            event = {"event_id": "d1", "decision_id": "d1", "message_type": "SHADOW_SIGNAL_BUY"}
            ledger.record(event, {"status": "SENT", "attempts": 1})
            self.assertTrue(ledger.already_sent(event))

    def test_11_experience_separation_and_phase20_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(Phase22LoopError):
                run_bounded_campaign_session(
                    max_candles=1,
                    store_root=PHASE20_DATA,
                    bar_source=lambda: ([], [], "2026-11-09 12:00:00"),
                    dry_run_discord=True,
                )
            exp = ExperienceStore(root)
            exp.add_shadow_from_outcome(
                {
                    "outcome_event_id": "x__H1",
                    "decision_id": "x",
                    "side": "BUY",
                    "status": "PASS",
                    "symbol": "XAUUSD",
                    "horizon_id": "H1",
                    "horizon_label": "5M",
                    "decision_timestamp_utc": "2026-11-09 12:00:00",
                    "realized_r": "1",
                    "outcome_timestamp_utc": "2026-11-09 12:05:00",
                }
            )
            exp.add_historical(
                {
                    "outcome_event_id": "h__H12",
                    "event_id": "h",
                    "side": "SELL",
                    "action": "SELL",
                    "outcome": "FAIL",
                    "realized_r": "-1",
                    "decision_timestamp_utc": "2026-01-01 10:00:00",
                    "outcome_timestamp_utc": "2026-01-01 11:00:00",
                }
            )
            self.assertEqual(exp.counts()["agent_shadow"], 1)
            self.assertEqual(exp.counts()["historical_hypothetical"], 1)

    def test_12_13_production_wait_holdout_orders(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(CANDIDATE_STATUS, "EXPERIMENTAL")
        self.assertEqual(BROKER_ORDERS, 0)
        self.assertEqual(HOLDOUT_ACCESSES, 0)
        self.assertGreater(PHASE21_HISTORICAL_BUY_RATE, 0)

    def test_14_integrity_and_report(self):
        report = verify_protected_hashes()
        self.assertTrue(report["all_ok"], msg=json.dumps({k: v for k, v in report["files"].items() if not v.get("ok")}, indent=2))
        integ = integrity_report()
        self.assertTrue(integ["frozen_thresholds_intact"])
        self.assertFalse(integ["github_push"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = CampaignStore(root).get_or_create(target=1000)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            rep = build_campaign_report(
                campaign_state=camp,
                store=store,
                experience=experience,
                diagnostics=DiagnosticJournal(root),
            )
            self.assertIn("phase21_comparison", rep)
            self.assertTrue(rep["synthetic_phase19_excluded"])

    def test_15_hard_failure_non_wait(self):
        bad = {
            "experimental_action": "BUY",
            "raw_action": "BUY",
            "final_action": "BUY",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "selected",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot": {},
            "feature_snapshot_json": "{}",
            "h1_context": {"h1_trend": "up"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bars = _bars(25)
            with patch("phase22.loop.predict_h13c_experimental", return_value=bad):
                with self.assertRaises(Phase22LoopError):
                    process_bar(
                        store=Phase18Store(root),
                        experience=ExperienceStore(root),
                        bar=bars[20],
                        closes_prefix=[float(b["close"]) for b in bars[:21]],
                        h1_rows=[{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40,
                        all_bars=bars,
                        as_of="2026-11-09 14:00:00",
                        prev_open=bars[19]["bar_open_timestamp_utc"],
                        discord_enabled=False,
                        dry_run_discord=True,
                        ledger=DeliveryLedger(root / "l.jsonl"),
                        diagnostics=DiagnosticJournal(root),
                        campaign_id="c",
                        session_id="s",
                    )


if __name__ == "__main__":
    unittest.main()
