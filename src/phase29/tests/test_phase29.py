"""Isolated Phase 29 tests (no live MT5; Discord dry-run / mocked only)."""

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

from phase16a.constants import FROZEN_CUTS
from phase18.experience import ExperienceStore
from phase20.candles import is_complete_m5_bar
from phase28.journals import ObserverJournal, OutcomeStore
from phase29.campaign import CampaignStore, evidence_status
from phase29.constants import (
    BROKER_ORDERS,
    HOLDOUT_ACCESSES,
    MIN_BUY_SELL_DECISIONS,
    MIN_FORWARD_CANDLES,
    MIN_MATURED_OUTCOMES,
    OBSERVER_A,
    OBSERVER_B,
    PRODUCTION_FINAL_ACTION,
)
from phase29.discord_notify import Phase29DeliveryLedger, deliver_decision, make_ledger
from phase29.integrity import frozen_thresholds_intact, integrity_report
from phase29.levels import planned_shadow_levels
from phase29.loop import Phase29LoopError, process_candle, run_bounded_live_shadow
from phase29.messages import (
    assert_concise_payload,
    build_buy_payload,
    build_sell_payload,
    build_wait_payload,
)
from phase29.observers import apply_high_only_policy, build_baseline_record, build_high_vol_record
from phase29.outcomes import pending_from_decision

UTC = timezone.utc


def _bar(open_utc: str, o=2000.0, h=2001.0, l=1999.0, c=2000.2) -> dict:
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
    }


def _bars(n: int = 80, start: datetime | None = None) -> list[dict]:
    t0 = start or datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    out = []
    for i in range(n):
        ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
        px = 2000 + i * 0.05
        out.append(_bar(ts, px, px + 1.0, px - 1.0, px + 0.2))
    return out


def _h1(n: int = 40) -> list[dict]:
    t0 = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
    out = []
    for i in range(n):
        open_ts = (t0 + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        close_ts = (t0 + timedelta(hours=i + 1)).strftime("%Y-%m-%d %H:%M:%S")
        px = 2000 + i * 0.1
        out.append(
            {
                "bar_open_timestamp_utc": open_ts,
                "bar_close_timestamp_utc": close_ts,
                "open": px,
                "high": px + 2,
                "low": px - 2,
                "close": px + 0.5,
                "time": open_ts,
            }
        )
    return out


def _fake_pred(action="WAIT", reason="wait"):
    return {
        "experimental_action": action,
        "raw_action": action,
        "final_action": "WAIT",
        "champion_status": "NO_MODEL",
        "experimental_reason": reason,
        "gate": {"gate_status": "BLOCK", "final_action": "WAIT"},
        "feature_snapshot": {"close_to_ema_20": -0.002, "ema_9_20_spread": 0.001},
        "h1_context": {"h1_trend": "up"},
        "frozen_cuts": {
            "close_ema_low": FROZEN_CUTS["close_ema_low"],
            "close_ema_high": FROZEN_CUTS["close_ema_high"],
            "q_low": 25,
            "q_high": 75,
            "source": FROZEN_CUTS["source"],
        },
    }


def _synth_vol_ok(regime="high"):
    return {"ok": True, "pred_fwd_vol_12": 0.001, "pred_vol_regime": regime}


class Phase29Tests(unittest.TestCase):
    def test_01_watermark_enforcement(self):
        bars = _bars(40)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = CampaignStore(root)
            st = camp.load()
            st["forward_observation_start_utc"] = "2026-11-10 19:00:00"
            camp.save(st)

            def src():
                return bars, _h1(), "2026-11-10 20:00:00"

            with patch("phase29.loop.verify_frozen_vol_ready", return_value={"ok": False}):
                with patch("phase29.loop.run_h13c_prediction", return_value=_fake_pred()):
                    result = run_bounded_live_shadow(
                        max_candles=10,
                        store_root=root,
                        bar_source=src,
                        discord_enabled=False,
                    )
            self.assertEqual(result["new_candles_processed"], 0)
            self.assertGreater(result["skipped_pre_start_candles"], 0)

    def test_02_forward_only_acceptance(self):
        bars = _bars(40)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = CampaignStore(root)
            st = camp.load()
            # Start before first bar so all injected bars count as forward.
            st["forward_observation_start_utc"] = "2026-11-10 07:59:00"
            camp.save(st)

            def src():
                return bars, _h1(), "2026-11-10 20:00:00"

            with patch("phase29.loop.verify_frozen_vol_ready", return_value={"ok": False}):
                with patch("phase29.loop.run_h13c_prediction", return_value=_fake_pred()):
                    result = run_bounded_live_shadow(
                        max_candles=5,
                        store_root=root,
                        bar_source=src,
                        discord_enabled=False,
                    )
            self.assertEqual(result["new_candles_processed"], 5)
            self.assertEqual(
                len(ObserverJournal(root / "observers" / OBSERVER_A, OBSERVER_A).read_all()),
                5,
            )

    def test_03_duplicate_candle_rejection(self):
        bars = _bars(30)
        dup = list(bars[:15]) + [dict(bars[10])] + list(bars[15:20])

        def src():
            return dup, _h1(), "2026-11-10 20:00:00"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = CampaignStore(root)
            st = camp.load()
            st["forward_observation_start_utc"] = "2026-11-10 07:59:00"
            camp.save(st)
            with patch("phase29.loop.verify_frozen_vol_ready", return_value={"ok": False}):
                with patch("phase29.loop.run_h13c_prediction", return_value=_fake_pred()):
                    with self.assertRaises(Phase29LoopError):
                        run_bounded_live_shadow(max_candles=20, store_root=root, bar_source=src)

    def test_04_restart_recovery(self):
        bars = _bars(40)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = CampaignStore(root)
            st = camp.load()
            st["forward_observation_start_utc"] = "2026-11-10 07:59:00"
            camp.save(st)

            def src():
                return bars, _h1(), "2026-11-10 20:00:00"

            with patch("phase29.loop.verify_frozen_vol_ready", return_value={"ok": False}):
                with patch("phase29.loop.run_h13c_prediction", return_value=_fake_pred()):
                    r1 = run_bounded_live_shadow(max_candles=3, store_root=root, bar_source=src)
                    r2 = run_bounded_live_shadow(max_candles=3, store_root=root, bar_source=src)
            self.assertEqual(r1["new_candles_processed"], 3)
            self.assertEqual(r2["new_candles_processed"], 3)
            self.assertEqual(CampaignStore(root).load()["new_candles_processed"], 6)
            self.assertEqual(
                CampaignStore(root).load()["forward_observation_start_utc"],
                "2026-11-10 07:59:00",
            )
            self.assertEqual(
                len(ObserverJournal(root / "observers" / OBSERVER_A, OBSERVER_A).read_all()),
                6,
            )

    def test_05_06_buy_sell_creation_and_levels(self):
        levels_buy = planned_shadow_levels(side="BUY", reference_price=4123.50, atr=2.0, spread_points=15)
        levels_sell = planned_shadow_levels(side="SELL", reference_price=4123.50, atr=2.0, spread_points=15)
        self.assertIn("entry", levels_buy)
        self.assertIn("tp_level", levels_buy)
        self.assertIn("sl_level", levels_buy)
        self.assertGreater(levels_buy["tp_level"], levels_buy["entry"])
        self.assertLess(levels_buy["sl_level"], levels_buy["entry"])
        self.assertLess(levels_sell["tp_level"], levels_sell["entry"])
        self.assertGreater(levels_sell["sl_level"], levels_sell["entry"])

        bar = _bar("2026-11-10 12:00:00", c=4123.50)
        buy = build_baseline_record(
            bar=bar,
            pred=_fake_pred("BUY", "buy_ok"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
            levels=levels_buy,
        )
        sell = build_baseline_record(
            bar=bar,
            pred=_fake_pred("SELL", "sell_ok"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
            levels=levels_sell,
        )
        self.assertEqual(buy["experimental_action"], "BUY")
        self.assertEqual(sell["experimental_action"], "SELL")
        self.assertEqual(buy["production_action"], "WAIT")
        self.assertIsNotNone(buy["entry"])
        self.assertIsNotNone(buy["tp_level"])
        self.assertIsNotNone(buy["sl_level"])

    def test_07_entry_tp_sl_presence_on_process(self):
        bars = _bars(50)
        bar = bars[40]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = make_ledger(root)
            with patch("phase29.loop.run_h13c_prediction", return_value=_fake_pred("BUY", "buy_ok")):
                with patch("phase29.loop.predict_vol_at_bar", return_value=_synth_vol_ok("high")):
                    with patch("phase29.loop.atr_at_signal", return_value=1.5):
                        r = process_candle(
                            root=root,
                            bar=bar,
                            all_m5=bars[:41],
                            h1_bars=_h1(),
                            closes_prefix=[float(b["close"]) for b in bars[:41]],
                            as_of="2026-11-10 20:00:00",
                            prev_open=bars[39]["bar_open_timestamp_utc"],
                            campaign_id="c",
                            session_id="s",
                            vol_artifact={"coef": [0] * 18},
                            ledger=ledger,
                            discord_enabled=True,
                            dry_run_discord=True,
                            notify_wait=False,
                        )
            dec = ObserverJournal(root / "observers" / OBSERVER_A, OBSERVER_A).read_all()[0]
            self.assertEqual(dec["experimental_action"], "BUY")
            self.assertIsNotNone(dec["entry"])
            self.assertIsNotNone(dec["tp_level"])
            self.assertIsNotNone(dec["sl_level"])
            self.assertEqual(dec["final_action"], PRODUCTION_FINAL_ACTION)
            self.assertEqual(r["discord"]["status"], "DRY_RUN")

    def test_08_09_10_discord_formats(self):
        levels = planned_shadow_levels(side="BUY", reference_price=4123.50, atr=2.0)
        bar = _bar("2026-11-10 13:35:00", c=4123.50)
        buy = build_baseline_record(
            bar=bar,
            pred=_fake_pred("BUY"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
            levels=levels,
        )
        sell_levels = planned_shadow_levels(side="SELL", reference_price=4123.50, atr=2.0)
        sell = build_baseline_record(
            bar=bar,
            pred=_fake_pred("SELL"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
            levels=sell_levels,
        )
        wait = build_baseline_record(
            bar=bar,
            pred=_fake_pred("WAIT"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
        )
        buy_c = build_buy_payload(buy)["content"]
        sell_c = build_sell_payload(sell)["content"]
        wait_c = build_wait_payload(wait)["content"]
        self.assertIn("**AIBOT — BUY 🟢**", buy_c)
        self.assertIn("**AIBOT — SELL 🔴**", sell_c)
        self.assertIn("**AIBOT — WAIT ⏸️**", wait_c)
        self.assertIn("Entry:", buy_c)
        self.assertIn("TP:", buy_c)
        self.assertIn("SL:", buy_c)
        for content in (buy_c, sell_c, wait_c):
            assert_concise_payload(content)
            self.assertIn("UTC", content)
            self.assertIn("PKT", content)
            self.assertIn(" | ", content)

    def test_11_utc_pkt_formatting(self):
        bar = _bar("2026-11-10 13:35:00")
        wait = build_baseline_record(
            bar=bar, pred=_fake_pred("WAIT"), gap_status="ok", campaign_id="c", session_id="s"
        )
        content = build_wait_payload(wait)["content"]
        # 13:40 UTC close → 18:40 PKT
        self.assertIn("13:40 UTC", content)
        self.assertIn("18:40 PKT", content)

    def test_12_13_outcome_maturity_and_idempotency(self):
        levels = planned_shadow_levels(side="BUY", reference_price=2000.0, atr=1.0)
        bar = _bar("2026-11-10 12:00:00")
        dec = build_baseline_record(
            bar=bar,
            pred=_fake_pred("BUY"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
            levels=levels,
        )
        rows = pending_from_decision(dec, atr=1.0)
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(all(r["status"] == "PENDING" for r in rows))
        with tempfile.TemporaryDirectory() as tmp:
            store = OutcomeStore(Path(tmp), OBSERVER_A)
            self.assertTrue(store.append(rows[0]))
            self.assertFalse(store.append(rows[0]))

    def test_14_15_experience_source_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "observers" / OBSERVER_A
            exp = ExperienceStore(root)
            self.assertEqual(exp.shadow_path.name, "agent_shadow_experience.jsonl")
            self.assertEqual(exp.historical_path.name, "historical_hypothetical_experience.jsonl")
            self.assertFalse(exp.historical_path.exists())

    def test_16_17_no_broker_and_production_wait(self):
        self.assertEqual(BROKER_ORDERS, 0)
        self.assertEqual(HOLDOUT_ACCESSES, 0)
        bad = _fake_pred("BUY")
        bad["final_action"] = "BUY"
        bars = _bars(40)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("phase29.loop.run_h13c_prediction", return_value=bad):
                with self.assertRaises(Phase29LoopError):
                    process_candle(
                        root=Path(tmp),
                        bar=bars[30],
                        all_m5=bars[:31],
                        h1_bars=_h1(),
                        closes_prefix=[float(b["close"]) for b in bars[:31]],
                        as_of="2026-11-10 20:00:00",
                        prev_open=bars[29]["bar_open_timestamp_utc"],
                        campaign_id="c",
                        session_id="s",
                        vol_artifact=None,
                        ledger=make_ledger(Path(tmp)),
                        discord_enabled=False,
                        dry_run_discord=True,
                        notify_wait=False,
                    )

    def test_18_high_only_isolation(self):
        bar = _bar("2026-11-10 12:00:00")
        levels = planned_shadow_levels(side="BUY", reference_price=2000.0, atr=1.0)
        high = build_high_vol_record(
            bar=bar,
            pred=_fake_pred("BUY"),
            vol=_synth_vol_ok("low"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
            levels=levels,
        )
        self.assertFalse(high["accepted"])
        self.assertEqual(high["production_action"], "WAIT")
        self.assertNotEqual(high["decision_id"], build_baseline_record(
            bar=bar, pred=_fake_pred("BUY"), gap_status="ok", campaign_id="c", session_id="s", levels=levels
        )["decision_id"])
        acc = apply_high_only_policy(h13c_action="BUY", pred_vol_regime="high", vol_ok=True)
        self.assertTrue(acc["accepted"])

    def test_19_no_historical_replay(self):
        self.assertFalse(is_complete_m5_bar(_bar("2026-11-10 12:00:00"), as_of_utc="2026-11-10 12:05:00"))
        self.assertTrue(is_complete_m5_bar(_bar("2026-11-10 12:00:00"), as_of_utc="2026-11-10 12:05:01"))

    def test_20_discord_idempotency(self):
        levels = planned_shadow_levels(side="BUY", reference_price=4123.50, atr=2.0)
        bar = _bar("2026-11-10 13:35:00", c=4123.50)
        dec = build_baseline_record(
            bar=bar,
            pred=_fake_pred("BUY"),
            gap_status="ok",
            campaign_id="c",
            session_id="s",
            levels=levels,
        )
        with tempfile.TemporaryDirectory() as tmp:
            ledger = make_ledger(Path(tmp))
            r1 = deliver_decision(
                decision=dec,
                ledger=ledger,
                discord_enabled=True,
                dry_run=True,
                notify_wait=False,
            )
            r2 = deliver_decision(
                decision=dec,
                ledger=ledger,
                discord_enabled=True,
                dry_run=True,
                notify_wait=False,
            )
            self.assertEqual(r1["status"], "DRY_RUN")
            self.assertEqual(r2["status"], "SKIPPED_DUPLICATE")

    def test_21_evidence_targets(self):
        ev = evidence_status(n_candles=0)
        self.assertEqual(ev["status"], "INSUFFICIENT_FORWARD_EVIDENCE")
        self.assertEqual(ev["gates"]["min_forward_candles"], MIN_FORWARD_CANDLES)
        self.assertEqual(ev["gates"]["min_buy_sell_decisions"], MIN_BUY_SELL_DECISIONS)
        self.assertEqual(ev["gates"]["min_matured_outcomes"], MIN_MATURED_OUTCOMES)

    def test_22_integrity_and_frozen_cuts(self):
        self.assertTrue(frozen_thresholds_intact())
        rep = integrity_report()
        self.assertEqual(rep["production_final_action"], "WAIT")
        self.assertEqual(rep["broker_order_count"], 0)
        self.assertTrue(rep["high_only_research_only"])

    def test_23_wait_skipped_on_discord_by_default(self):
        bar = _bar("2026-11-10 13:35:00")
        wait = build_baseline_record(
            bar=bar, pred=_fake_pred("WAIT"), gap_status="ok", campaign_id="c", session_id="s"
        )
        with tempfile.TemporaryDirectory() as tmp:
            ledger = make_ledger(Path(tmp))
            r = deliver_decision(
                decision=wait,
                ledger=ledger,
                discord_enabled=True,
                dry_run=True,
                notify_wait=False,
            )
            self.assertEqual(r["status"], "SKIPPED_WAIT")


if __name__ == "__main__":
    unittest.main()
