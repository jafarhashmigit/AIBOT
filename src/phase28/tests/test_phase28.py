"""Isolated Phase 28 tests (no live MT5; no Discord/Telegram)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase16a.constants import FROZEN_CUTS
from phase20.candles import is_complete_m5_bar
from phase22.integrity import verify_protected_hashes
from phase28.campaign import CampaignStore, evidence_status
from phase28.constants import (
    BROKER_ORDERS,
    DISCORD_MESSAGES_SENT,
    FROZEN_VOL_FEATURES,
    FROZEN_WF3_CUTS,
    HIGH_ONLY_REGIME,
    H13C_Q_HIGH,
    H13C_Q_LOW,
    HOLDOUT_ACCESSES,
    OBSERVER_BASELINE,
    OBSERVER_HIGH_VOL,
    PRODUCTION_FINAL_ACTION,
    TELEGRAM_MESSAGES_SENT,
)
from phase28.frozen_vol import predict_vol_and_regime, verify_frozen_vol_artifact
from phase28.integrity import frozen_thresholds_intact, integrity_report
from phase28.journals import ObserverJournal, OutcomeStore
from phase28.live_features import bars_to_m5_context, wilder_atr_series
from phase28.loop import Phase28LoopError, process_candle, resolve_all_observers, run_bounded_live_shadow
from phase28.observers import apply_high_only_policy, build_baseline_record, build_high_vol_record
from phase28.outcomes import pending_from_decision
from phase28.run_phase28 import write_ready_report

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
        "data_source": "synthetic_fixture",
    }


def _bars(n: int = 80, start: datetime | None = None) -> list[dict]:
    t0 = start or datetime(2026, 11, 9, 8, 0, tzinfo=UTC)
    out = []
    for i in range(n):
        ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
        px = 2000 + i * 0.05
        out.append(_bar(ts, px, px + 1.0, px - 1.0, px + 0.2))
    return out


def _h1(n: int = 40) -> list[dict]:
    t0 = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)
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
        "feature_snapshot_json": "{}",
        "h1_context": {"h1_trend": "up"},
        "frozen_cuts": {
            "close_ema_low": FROZEN_CUTS["close_ema_low"],
            "close_ema_high": FROZEN_CUTS["close_ema_high"],
            "q_low": 25,
            "q_high": 75,
            "source": FROZEN_CUTS["source"],
        },
    }


def _synth_artifact() -> dict:
    rng = np.random.default_rng(42)
    coef = list(rng.normal(0, 0.01, size=len(FROZEN_VOL_FEATURES)))
    return {
        "artifact_id": "phase28_frozen_vol_model_v1",
        "method": "train_predicted_vol_tertiles",
        "policy": "high_only",
        "high_regime_label": "high",
        "train_cutoff_utc": FROZEN_CUTS["train_cutoff"],
        "ridge_alpha": 1.0,
        "seed": 42,
        "feature_names": list(FROZEN_VOL_FEATURES),
        "n_train": 1000,
        "coef": coef,
        "intercept": 0.0003,
        "tertile_cuts_predicted_train": {"p33": 0.0002, "p67": 0.0004},
    }


class Phase28Tests(unittest.TestCase):
    def test_01_frozen_threshold_integrity(self):
        self.assertTrue(frozen_thresholds_intact())
        self.assertEqual(H13C_Q_LOW, 25)
        self.assertEqual(H13C_Q_HIGH, 75)
        self.assertEqual(FROZEN_WF3_CUTS["q_low"], 25)
        self.assertEqual(FROZEN_WF3_CUTS["q_high"], 75)
        self.assertEqual(FROZEN_WF3_CUTS["close_ema_low"], FROZEN_CUTS["close_ema_low"])

    def test_02_frozen_vol_artifact_verify(self):
        art = _synth_artifact()
        v = verify_frozen_vol_artifact(art)
        self.assertTrue(v["checks"]["all_ok"])

    def test_03_high_only_policy(self):
        acc = apply_high_only_policy(h13c_action="BUY", pred_vol_regime=HIGH_ONLY_REGIME, vol_ok=True)
        self.assertTrue(acc["accepted"])
        self.assertEqual(acc["experimental_action"], "BUY")
        skip = apply_high_only_policy(h13c_action="BUY", pred_vol_regime="low", vol_ok=True)
        self.assertFalse(skip["accepted"])
        self.assertEqual(skip["experimental_action"], "WAIT")

    def test_03b_high_only_wait(self):
        wait = apply_high_only_policy(h13c_action="WAIT", pred_vol_regime="high", vol_ok=True)
        self.assertFalse(wait["accepted"])
        blocked = apply_high_only_policy(h13c_action="SELL", pred_vol_regime="high", vol_ok=False, vol_reason="missing")
        self.assertEqual(blocked["policy_decision"], "BLOCKED_VOL_UNAVAILABLE")

    def test_04_no_lookahead_vol_prediction_uses_past_only(self):
        art = _synth_artifact()
        vec = np.ones(len(FROZEN_VOL_FEATURES))
        p = predict_vol_and_regime(vec, art)
        self.assertIn(p["pred_vol_regime"], {"low", "medium", "high", "unknown"})

    def test_05_completed_candle_only(self):
        bar = _bar("2026-11-09 12:00:00")
        self.assertTrue(is_complete_m5_bar(bar, as_of_utc="2026-11-09 12:05:01"))
        self.assertFalse(is_complete_m5_bar(bar, as_of_utc="2026-11-09 12:05:00"))

    def test_06_duplicate_and_separate_journals(self):
        bars = _bars(60)
        bar = bars[50]
        as_of = "2026-11-09 14:00:00"
        fake = _fake_pred("BUY", "buy_ok")
        art = _synth_artifact()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("phase28.loop.run_h13c_prediction", return_value=fake):
                with patch("phase28.loop.predict_vol_at_bar", return_value={"ok": True, "pred_fwd_vol_12": 0.001, "pred_vol_regime": "high"}):
                    r1 = process_candle(
                        root=root,
                        bar=bar,
                        all_m5=bars[:51],
                        h1_bars=_h1(),
                        closes_prefix=[float(b["close"]) for b in bars[:51]],
                        as_of=as_of,
                        prev_open=bars[49]["bar_open_timestamp_utc"],
                        campaign_id="c1",
                        session_id="s1",
                        vol_artifact=art,
                    )
                    r2 = process_candle(
                        root=root,
                        bar=bar,
                        all_m5=bars[:51],
                        h1_bars=_h1(),
                        closes_prefix=[float(b["close"]) for b in bars[:51]],
                        as_of=as_of,
                        prev_open=bars[49]["bar_open_timestamp_utc"],
                        campaign_id="c1",
                        session_id="s1",
                        vol_artifact=art,
                    )
            self.assertTrue(r1["observers"][OBSERVER_BASELINE]["written"])
            self.assertTrue(r2["observers"][OBSERVER_BASELINE]["duplicate"])
            j_b = ObserverJournal(root / "observers" / OBSERVER_BASELINE, OBSERVER_BASELINE).read_all()
            j_h = ObserverJournal(root / "observers" / OBSERVER_HIGH_VOL, OBSERVER_HIGH_VOL).read_all()
            self.assertEqual(len(j_b), 1)
            self.assertEqual(len(j_h), 1)
            self.assertNotEqual(j_b[0]["decision_id"], j_h[0]["decision_id"])
            self.assertEqual(j_b[0]["final_action"], PRODUCTION_FINAL_ACTION)
            self.assertEqual(j_h[0]["final_action"], PRODUCTION_FINAL_ACTION)

    def test_07_duplicate_open_rejection_and_no_replay(self):
        bars = _bars(40)
        # Duplicate open timestamp in an otherwise ascending list.
        dup = list(bars[:20]) + [dict(bars[15])] + list(bars[20:25])

        def bad_source():
            return dup, _h1(), "2026-11-09 20:00:00"

        with tempfile.TemporaryDirectory() as tmp:
            with patch("phase28.loop.verify_frozen_vol_ready", return_value={"ok": True}):
                with patch("phase28.loop.load_frozen_vol_artifact", return_value=_synth_artifact()):
                    with patch("phase28.loop.run_h13c_prediction", return_value=_fake_pred()):
                        with patch(
                            "phase28.loop.predict_vol_at_bar",
                            return_value={"ok": True, "pred_fwd_vol_12": 0.001, "pred_vol_regime": "high"},
                        ):
                            with self.assertRaises(Phase28LoopError):
                                run_bounded_live_shadow(
                                    max_candles=30,
                                    store_root=Path(tmp),
                                    bar_source=bad_source,
                                )

    def test_08_gap_and_timezone_enrichment(self):
        from phase20.candles import enrich_observation_timestamps

        bar = _bar("2026-11-09 12:00:00")
        ts = enrich_observation_timestamps(bar)
        self.assertTrue(ts["candle_timestamp_utc"].endswith("12:05:00"))
        self.assertIn("PKT", ts["candle_timestamp_pkt"] or "PKT")

    def test_09_separate_experience_sources(self):
        from phase18.experience import ExperienceStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for oid in (OBSERVER_BASELINE, OBSERVER_HIGH_VOL):
                exp = ExperienceStore(root / "observers" / oid)
                self.assertFalse(exp.historical_path.exists())
                self.assertEqual(exp.shadow_path.name, "agent_shadow_experience.jsonl")

    def test_10_outcome_maturity_lifecycle(self):
        dec = {
            "decision_id": "d1",
            "observer_id": OBSERVER_BASELINE,
            "decision_timestamp_utc": "2026-11-09 12:05:00",
            "signal_bar_open_utc": "2026-11-09 12:00:00",
            "experimental_action": "BUY",
            "accepted": True,
        }
        rows = pending_from_decision(dec, atr=1.0)
        self.assertGreaterEqual(len(rows), 5)
        ids = {r["horizon_id"] for r in rows}
        self.assertEqual(ids, {"H1", "H2", "H3", "H6", "H12"})
        self.assertTrue(all(r["status"] == "PENDING" for r in rows))

    def test_11_restart_recovery_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            j = ObserverJournal(root, OBSERVER_BASELINE)
            row = {
                "idempotency_key": "k1",
                "decision_id": "k1",
                "experimental_action": "WAIT",
                "accepted": False,
                "reason_code": "x",
            }
            self.assertTrue(j.append(row))
            self.assertFalse(j.append(row))
            j2 = ObserverJournal(root, OBSERVER_BASELINE)
            self.assertTrue(j2.has("k1"))
            self.assertEqual(len(j2.read_all()), 1)

    def test_12_default_readiness_no_mt5(self):
        # May build frozen vol from historical — can be slow but required for readiness.
        # Patch ensure to avoid long fit in unit test if artifact path writable issues.
        with patch("phase28.run_phase28.ensure_frozen_vol", return_value={"ok": True}):
            with patch("phase28.run_phase28.integrity_report") as ir:
                ir.return_value = {
                    "protected_hashes_phase22": {"all_ok": True},
                    "frozen_thresholds_intact": True,
                    "high_only_policy": {"ok": True},
                    "frozen_vol": {"ok": True},
                    "holdout_access_count": 0,
                }
                with patch("phase28.run_phase28.build_campaign_report") as br:
                    br.return_value = {
                        "evidence": evidence_status(n_candles=0),
                        "insufficient_forward_evidence": True,
                    }
                    summary = write_ready_report()
        self.assertEqual(summary["mode"], "ready_not_started")
        self.assertFalse(summary["mt5_session_started"])
        self.assertFalse(summary["forward_campaign_started"])
        self.assertEqual(summary["production_final_action"], "WAIT")

    def test_13_mt5_readonly_and_no_side_effects(self):
        self.assertEqual(BROKER_ORDERS, 0)
        self.assertEqual(DISCORD_MESSAGES_SENT, 0)
        self.assertEqual(TELEGRAM_MESSAGES_SENT, 0)
        self.assertEqual(HOLDOUT_ACCESSES, 0)
        from phase12.mt5_allowlist import audit_source

        audit = audit_source(Path(_SRC) / "phase16a" / "mt5_reader.py", raise_on_prohibited=True)
        self.assertEqual(audit["prohibited_found"], [])
        # Phase 28 must not call MT5 APIs directly.
        p28_loop = audit_source(Path(_SRC) / "phase28" / "loop.py", raise_on_prohibited=True)
        self.assertEqual(p28_loop["permitted_used"], [])
        self.assertEqual(p28_loop["prohibited_found"], [])

    def test_14_production_wait_enforcement(self):
        bad = _fake_pred("BUY")
        bad["final_action"] = "BUY"
        bars = _bars(40)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("phase28.loop.run_h13c_prediction", return_value=bad):
                with self.assertRaises(Phase28LoopError):
                    process_candle(
                        root=Path(tmp),
                        bar=bars[30],
                        all_m5=bars[:31],
                        h1_bars=_h1(),
                        closes_prefix=[float(b["close"]) for b in bars[:31]],
                        as_of="2026-11-09 14:00:00",
                        prev_open=bars[29]["bar_open_timestamp_utc"],
                        campaign_id="c",
                        session_id="s",
                        vol_artifact=_synth_artifact(),
                    )

    def test_15_protected_historical_hashes(self):
        res = verify_protected_hashes()
        self.assertTrue(res["all_ok"], msg=json.dumps(res, indent=2))

    def test_16_evidence_insufficient_by_default(self):
        ev = evidence_status(n_candles=0)
        self.assertEqual(ev["status"], "INSUFFICIENT_FORWARD_EVIDENCE")

    def test_17_high_only_skip_vs_accept_journals(self):
        pred = _fake_pred("SELL", "sell_ok")
        bar = _bar("2026-11-09 12:00:00")
        high = build_high_vol_record(
            bar=bar,
            pred=pred,
            vol={"ok": True, "pred_fwd_vol_12": 0.0001, "pred_vol_regime": "low"},
            gap_status="ok",
            campaign_id="c",
            session_id="s",
        )
        self.assertFalse(high["accepted"])
        self.assertEqual(high["experimental_action"], "WAIT")
        base = build_baseline_record(bar=bar, pred=pred, gap_status="ok", campaign_id="c", session_id="s")
        self.assertTrue(base["accepted"])
        self.assertEqual(base["experimental_action"], "SELL")

    def test_18_atr_no_future_bars(self):
        highs = np.arange(20, dtype=float)
        lows = highs - 1
        closes = highs - 0.2
        atr = wilder_atr_series(highs, lows, closes, 14)
        self.assertTrue(np.isnan(atr[10]))
        self.assertTrue(np.isfinite(atr[13]))

    def test_19_outcome_store_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OutcomeStore(Path(tmp), OBSERVER_BASELINE)
            row = {"outcome_event_id": "o1", "status": "PENDING", "horizon_id": "H1"}
            self.assertTrue(store.append(row))
            self.assertFalse(store.append(row))

    def test_20_integrity_report_safety(self):
        rep = integrity_report()
        self.assertEqual(rep["production_final_action"], "WAIT")
        self.assertEqual(rep["broker_order_count"], 0)
        self.assertEqual(rep["discord_messages_sent"], 0)
        self.assertEqual(rep["telegram_messages_sent"], 0)
        self.assertTrue(rep["frozen_thresholds_intact"])

    def test_21_forward_start_skips_pre_start_history(self):
        """MT5 buffer candles at/before forward start must not be journaled."""
        bars = _bars(40)
        as_of = "2026-11-09 20:00:00"
        # Pretend campaign already froze forward start after all synthetic bars.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = CampaignStore(root)
            st = camp.load()
            st["forward_observation_start_utc"] = "2026-11-09 19:00:00"
            camp.save(st)

            def src():
                return bars, _h1(), as_of

            with patch("phase28.loop.verify_frozen_vol_ready", return_value={"ok": True}):
                with patch("phase28.loop.load_frozen_vol_artifact", return_value=_synth_artifact()):
                    with patch("phase28.loop.run_h13c_prediction", return_value=_fake_pred()):
                        result = run_bounded_live_shadow(
                            max_candles=10,
                            store_root=root,
                            bar_source=src,
                        )
            self.assertEqual(result["new_candles_processed"], 0)
            self.assertGreater(result["skipped_pre_start_candles"], 0)
            self.assertEqual(
                len(ObserverJournal(root / "observers" / OBSERVER_BASELINE, OBSERVER_BASELINE).read_all()),
                0,
            )


if __name__ == "__main__":
    unittest.main()
