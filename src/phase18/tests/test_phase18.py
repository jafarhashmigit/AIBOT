"""Deterministic Phase 18 multi-horizon shadow learning tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parents[2]
import sys

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase18.barrier import BUY, SELL, market_arrays_from_bars, simulate_trade_horizon, wilder_atr
from phase18.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    CANDIDATE_STATUS,
    FORBIDDEN_SIGNAL_PHRASES,
    HOLDOUT_ACCESSES,
    HORIZONS,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_PENDING,
    OUTCOME_TIMEOUT,
    SELECTED_HORIZON_DISPLAY,
    SOURCE_HISTORICAL,
    SOURCE_SHADOW,
)
from phase18.daily_report import aggregate_daily, build_daily_discord_bundle, daily_report_id
from phase18.experience import ExperienceStore
from phase18.horizons import expected_outcome_check_pkt, expected_outcome_check_utc, horizon_label
from phase18.integrity import integrity_report, verify_protected_hashes
from phase18.loop import process_bar, recover_on_startup, resolve_pending_outcomes, run_bounded_multihorizon_loop
from phase18.messages import assert_no_guarantee_language, build_outcome_payload, build_signal_payload
from phase18.outcomes import atr_at_signal, create_pending_outcomes, evaluate_horizon_outcome, map_exit_to_state
from phase18.store import Phase18Store
from phase16b.dedupe import DeliveryLedger


UTC = timezone.utc


def _bar(open_utc: str, o: float, h: float, l: float, c: float, spread: float = 20.0) -> dict:
    close_dt = datetime.strptime(open_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) + timedelta(minutes=5)
    return {
        "bar_open_timestamp_utc": open_utc,
        "bar_close_timestamp_utc": close_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "spread": spread,
        "tick_volume": 100,
        "data_source": "synthetic",
        "source_timezone": "UTC",
        "conversion": "already_utc",
        "source_stamp": open_utc,
    }


def _make_history(n: int = 40, start: str = "2026-11-09 10:00:00", base: float = 2000.0) -> list[dict]:
    """Flatish series with enough bars for ATR."""
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    bars = []
    px = base
    for i in range(n):
        ts = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
        # mild oscillation
        delta = 0.4 if i % 2 == 0 else -0.3
        o = px
        c = px + delta
        h = max(o, c) + 0.5
        l = min(o, c) - 0.5
        bars.append(_bar(ts, o, h, l, c))
        px = c
    return bars


def _force_tp_buy_path(bars: list[dict], signal_idx: int, atr: float) -> list[dict]:
    """Mutate entry+path so BUY hits TP within first bar of horizon."""
    out = [dict(b) for b in bars]
    entry = signal_idx + 1
    # approximate entry fill ~ open+spread+$0.05; push high far above
    out[entry]["open"] = out[signal_idx]["close"]
    out[entry]["low"] = out[entry]["open"] - 0.1
    out[entry]["high"] = out[entry]["open"] + atr * 3.0
    out[entry]["close"] = out[entry]["open"] + atr
    return out


def _force_sl_buy_path(bars: list[dict], signal_idx: int, atr: float) -> list[dict]:
    out = [dict(b) for b in bars]
    entry = signal_idx + 1
    out[entry]["open"] = out[signal_idx]["close"]
    out[entry]["high"] = out[entry]["open"] + 0.1
    out[entry]["low"] = out[entry]["open"] - atr * 3.0
    out[entry]["close"] = out[entry]["open"] - atr
    return out


def _force_timeout_buy_path(bars: list[dict], signal_idx: int, horizon_bars: int) -> list[dict]:
    out = [dict(b) for b in bars]
    for k in range(signal_idx + 1, signal_idx + 1 + horizon_bars):
        if k >= len(out):
            break
        out[k]["open"] = out[signal_idx]["close"]
        out[k]["high"] = out[k]["open"] + 0.05
        out[k]["low"] = out[k]["open"] - 0.05
        out[k]["close"] = out[k]["open"]
    return out


class Phase18Tests(unittest.TestCase):
    def test_01_to_05_horizons_defined(self):
        self.assertEqual(HORIZONS["H1"], 1)
        self.assertEqual(HORIZONS["H2"], 2)
        self.assertEqual(HORIZONS["H3"], 3)
        self.assertEqual(HORIZONS["H6"], 6)
        self.assertEqual(HORIZONS["H12"], 12)
        self.assertEqual(horizon_label("H1"), "5M")
        self.assertEqual(horizon_label("H2"), "10M")
        self.assertEqual(horizon_label("H3"), "15M")
        self.assertEqual(horizon_label("H6"), "30M")
        self.assertEqual(horizon_label("H12"), "60M")

    def test_06_outcome_timing(self):
        close = "2026-11-09 12:35:00"
        self.assertEqual(expected_outcome_check_utc(close, "H1"), "2026-11-09 12:40:00")
        self.assertEqual(expected_outcome_check_utc(close, "H2"), "2026-11-09 12:45:00")
        self.assertEqual(expected_outcome_check_utc(close, "H3"), "2026-11-09 12:50:00")
        self.assertEqual(expected_outcome_check_utc(close, "H6"), "2026-11-09 13:05:00")
        self.assertEqual(expected_outcome_check_utc(close, "H12"), "2026-11-09 13:35:00")

    def test_07_08_09_pass_fail_timeout(self):
        self.assertEqual(map_exit_to_state("TP"), OUTCOME_PASS)
        self.assertEqual(map_exit_to_state("SL"), OUTCOME_FAIL)
        self.assertEqual(map_exit_to_state("TIME"), OUTCOME_TIMEOUT)

        bars = _make_history(40)
        signal_idx = 20
        atr = atr_at_signal(bars, signal_idx)

        for hid, hbars in HORIZONS.items():
            # PASS
            path = _force_tp_buy_path(bars, signal_idx, atr)
            # ensure enough future bars
            self.assertGreaterEqual(len(path), signal_idx + 1 + hbars)
            pending = {
                "outcome_event_id": f"e_{hid}",
                "decision_id": "d1",
                "horizon_id": hid,
                "horizon_label": horizon_label(hid),
                "horizon_bars": hbars,
                "side": "BUY",
                "symbol": "XAUUSD",
                "decision_timestamp_utc": path[signal_idx]["bar_close_timestamp_utc"],
                "expected_check_utc": expected_outcome_check_utc(path[signal_idx]["bar_close_timestamp_utc"], hid),
                "status": OUTCOME_PENDING,
            }
            as_of = path[signal_idx + hbars]["bar_close_timestamp_utc"]
            got = evaluate_horizon_outcome(
                pending,
                bars=path,
                signal_bar_open_utc=path[signal_idx]["bar_open_timestamp_utc"],
                atr=atr,
                as_of_utc=as_of,
            )
            self.assertEqual(got["status"], OUTCOME_PASS, hid)
            self.assertEqual(got["exit_reason"], "TP")

            # FAIL
            path_sl = _force_sl_buy_path(bars, signal_idx, atr)
            got_sl = evaluate_horizon_outcome(
                pending,
                bars=path_sl,
                signal_bar_open_utc=path_sl[signal_idx]["bar_open_timestamp_utc"],
                atr=atr,
                as_of_utc=as_of,
            )
            self.assertEqual(got_sl["status"], OUTCOME_FAIL, hid)

            # TIMEOUT
            path_to = _force_timeout_buy_path(bars, signal_idx, hbars)
            got_to = evaluate_horizon_outcome(
                pending,
                bars=path_to,
                signal_bar_open_utc=path_to[signal_idx]["bar_open_timestamp_utc"],
                atr=atr,
                as_of_utc=as_of,
            )
            self.assertEqual(got_to["status"], OUTCOME_TIMEOUT, hid)

    def test_10_pending_when_incomplete(self):
        bars = _make_history(25)
        signal_idx = 20
        atr = atr_at_signal(bars, signal_idx)
        pending = {
            "outcome_event_id": "e_h12",
            "decision_id": "d1",
            "horizon_id": "H12",
            "horizon_label": "60M",
            "horizon_bars": 12,
            "side": "BUY",
            "symbol": "XAUUSD",
            "decision_timestamp_utc": bars[signal_idx]["bar_close_timestamp_utc"],
            "expected_check_utc": expected_outcome_check_utc(bars[signal_idx]["bar_close_timestamp_utc"], "H12"),
            "status": OUTCOME_PENDING,
        }
        # Only a few bars after signal — H12 not ready
        short = bars[: signal_idx + 3]
        got = evaluate_horizon_outcome(
            pending,
            bars=short,
            signal_bar_open_utc=bars[signal_idx]["bar_open_timestamp_utc"],
            atr=atr,
            as_of_utc=bars[signal_idx + 2]["bar_close_timestamp_utc"],
        )
        self.assertEqual(got["status"], OUTCOME_PENDING)

    def test_11_wait_creates_no_trade_outcome(self):
        dec = {
            "decision_id": "d_wait",
            "experimental_action": "WAIT",
            "decision_timestamp_utc": "2026-11-09 12:00:00",
            "symbol": "XAUUSD",
        }
        self.assertEqual(create_pending_outcomes(dec), [])

    def test_12_13_buy_and_sell_outcomes(self):
        bars = _make_history(40)
        signal_idx = 20
        atr = atr_at_signal(bars, signal_idx)
        m = market_arrays_from_bars(bars)
        buy = simulate_trade_horizon(m, BUY, signal_idx, atr, horizon_bars=3)
        sell = simulate_trade_horizon(m, SELL, signal_idx, atr, horizon_bars=3)
        self.assertEqual(buy["side"], "BUY")
        self.assertEqual(sell["side"], "SELL")
        self.assertIn(buy["exit_reason"], {"TP", "SL", "TIME"})
        self.assertIn(sell["exit_reason"], {"TP", "SL", "TIME"})

    def test_14_15_experience_source_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp))
            shadow = store.add_shadow_from_outcome(
                {
                    "outcome_event_id": "dec1__H3",
                    "decision_id": "dec1",
                    "side": "BUY",
                    "status": "PASS",
                    "symbol": "XAUUSD",
                    "horizon_id": "H3",
                    "horizon_label": "15M",
                    "decision_timestamp_utc": "2026-11-09 12:00:00",
                    "realized_r": "1.0",
                    "outcome_timestamp_utc": "2026-11-09 12:15:00",
                }
            )
            hist = store.add_historical(
                {
                    "outcome_event_id": "hist1__H12",
                    "event_id": "hist1",
                    "decision_id": "hist1",
                    "side": "SELL",
                    "action": "SELL",
                    "outcome": "FAIL",
                    "realized_r": "-1.0",
                    "decision_timestamp_utc": "2026-01-01 10:00:00",
                    "outcome_timestamp_utc": "2026-01-01 11:00:00",
                }
            )
            self.assertEqual(shadow["source"], SOURCE_SHADOW)
            self.assertEqual(hist["source"], SOURCE_HISTORICAL)
            self.assertNotEqual(shadow["experience_id"], hist["experience_id"])
            self.assertEqual(store.counts()["agent_shadow"], 1)
            self.assertEqual(store.counts()["historical_hypothetical"], 1)
            # no silent merge
            self.assertTrue(all(r["source"] == SOURCE_SHADOW for r in store.list_shadow()))
            self.assertTrue(all(r["source"] == SOURCE_HISTORICAL for r in store.list_historical()))

    def test_16_17_pass_and_fail_experience_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp))
            for status, oid in (("PASS", "a__H1"), ("FAIL", "b__H1")):
                row = store.add_shadow_from_outcome(
                    {
                        "outcome_event_id": oid,
                        "decision_id": oid.split("__")[0],
                        "side": "BUY",
                        "status": status,
                        "symbol": "XAUUSD",
                        "horizon_id": "H1",
                        "horizon_label": "5M",
                        "decision_timestamp_utc": "2026-11-09 12:00:00",
                        "realized_r": "1.0" if status == "PASS" else "-1.0",
                        "outcome_timestamp_utc": "2026-11-09 12:05:00",
                    }
                )
                self.assertIsNotNone(row)
                self.assertEqual(row["outcome"], status)
            self.assertEqual(store.counts()["agent_shadow"], 2)

    def test_18_duplicate_outcome_prevention(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Phase18Store(Path(tmp))
            rows = create_pending_outcomes(
                {
                    "decision_id": "d1",
                    "experimental_action": "BUY",
                    "decision_timestamp_utc": "2026-11-09 12:00:00",
                    "symbol": "XAUUSD",
                }
            )
            self.assertEqual(store.append_outcomes(rows), 5)
            self.assertEqual(store.append_outcomes(rows), 0)

    def test_19_duplicate_discord_prevention(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DeliveryLedger(Path(tmp) / "ledger.jsonl")
            event = {"event_id": "d1", "decision_id": "d1", "message_type": "SHADOW_SIGNAL_BUY"}
            self.assertFalse(ledger.already_sent(event))
            ledger.record(event, {"status": "SENT", "attempts": 1})
            self.assertTrue(ledger.already_sent(event))

    def test_20_restart_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            ledger = DeliveryLedger(root / "ledger.jsonl")
            bars = _make_history(40)
            signal_idx = 20
            atr = atr_at_signal(bars, signal_idx)
            path = _force_tp_buy_path(bars, signal_idx, atr)
            dec = {
                "decision_id": "p18_dec_recover",
                "observation_id": "obs",
                "source_type": "FORWARD_SHADOW",
                "decision_timestamp_utc": path[signal_idx]["bar_close_timestamp_utc"],
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "model_id": "no_model",
                "model_status": CHAMPION_STATUS,
                "candidate_id": "H13_C_H1_PULLBACK",
                "candidate_status": CANDIDATE_STATUS,
                "experimental_action": "BUY",
                "raw_action": "BUY",
                "risk_gate_result": "ALLOW",
                "final_action": "WAIT",
                "decision_reason": "test",
                "feature_snapshot_json": "{}",
                "selected_horizon": SELECTED_HORIZON_DISPLAY,
                "outcome_status": "pending_multi_horizon",
                "signal_bar_open_utc": path[signal_idx]["bar_open_timestamp_utc"],
                "atr": f"{atr:.8f}",
                "tp_level": "",
                "sl_level": "",
                "is_paper_trade": False,
                "is_paper_execution": False,
                "note": "recovery test",
            }
            store.append_decision(dec)
            store.append_outcomes(create_pending_outcomes(dec, atr=atr))
            # Simulate restart: resolve without replaying signal Discord
            as_of = path[signal_idx + 12]["bar_close_timestamp_utc"]
            stats = recover_on_startup(
                store=store,
                experience=experience,
                bars=path,
                as_of=as_of,
                discord_enabled=True,
                dry_run_discord=True,
                ledger=ledger,
            )
            self.assertGreaterEqual(len(stats["finalized"]), 1)
            # Second recovery must not duplicate experience
            before = experience.counts()["agent_shadow"]
            recover_on_startup(
                store=store,
                experience=experience,
                bars=path,
                as_of=as_of,
                discord_enabled=True,
                dry_run_discord=True,
                ledger=ledger,
            )
            self.assertEqual(experience.counts()["agent_shadow"], before)

    def test_21_pkt_daily_aggregation(self):
        # 18:00 UTC = 23:00 PKT on 2026-11-09; 19:00 UTC = 00:00 PKT next day
        decisions = [
            {
                "decision_id": "d_same",
                "experimental_action": "BUY",
                "decision_timestamp_utc": "2026-11-09 18:00:00",
            },
            {
                "decision_id": "d_next",
                "experimental_action": "SELL",
                "decision_timestamp_utc": "2026-11-09 19:00:00",
            },
            {
                "decision_id": "d_wait",
                "experimental_action": "WAIT",
                "decision_timestamp_utc": "2026-11-09 17:00:00",
            },
        ]
        outcomes = [
            {
                "decision_id": "d_same",
                "horizon_id": "H1",
                "status": OUTCOME_PASS,
                "side": "BUY",
                "realized_r": "1.0",
            },
            {
                "decision_id": "d_same",
                "horizon_id": "H2",
                "status": OUTCOME_PENDING,
                "side": "BUY",
                "realized_r": "",
            },
        ]
        report = aggregate_daily(decisions=decisions, outcomes=outcomes, date_pkt="2026-11-09")
        self.assertEqual(report["signals"]["BUY"], 1)
        self.assertEqual(report["signals"]["WAIT"], 1)
        self.assertEqual(report["signals"]["SELL"], 0)  # next PKT day
        self.assertEqual(report["outcomes_by_horizon"]["H1"][OUTCOME_PASS], 1)
        self.assertEqual(report["outcomes_by_horizon"]["H2"][OUTCOME_PENDING], 1)

    def test_22_pending_excluded_from_pass_fail_rate(self):
        decisions = [
            {"decision_id": "d1", "experimental_action": "BUY", "decision_timestamp_utc": "2026-11-09 10:00:00"}
        ]
        outcomes = [
            {"decision_id": "d1", "horizon_id": "H1", "status": OUTCOME_PASS, "side": "BUY", "realized_r": "1"},
            {"decision_id": "d1", "horizon_id": "H2", "status": OUTCOME_FAIL, "side": "BUY", "realized_r": "-1"},
            {"decision_id": "d1", "horizon_id": "H3", "status": OUTCOME_PENDING, "side": "BUY", "realized_r": ""},
            {"decision_id": "d1", "horizon_id": "H6", "status": OUTCOME_TIMEOUT, "side": "BUY", "realized_r": "0.1"},
        ]
        report = aggregate_daily(decisions=decisions, outcomes=outcomes, date_pkt="2026-11-09")
        self.assertEqual(report["performance"]["resolved_pass_fail_n"], 2)
        self.assertAlmostEqual(report["performance"]["pass_fail_rate_pct"], 50.0)

    def test_23_wait_excluded_from_trade_stats(self):
        decisions = [
            {"decision_id": "w1", "experimental_action": "WAIT", "decision_timestamp_utc": "2026-11-09 10:00:00"},
            {"decision_id": "b1", "experimental_action": "BUY", "decision_timestamp_utc": "2026-11-09 10:05:00"},
        ]
        report = aggregate_daily(decisions=decisions, outcomes=[], date_pkt="2026-11-09")
        self.assertEqual(report["signals"]["WAIT"], 1)
        self.assertEqual(report["signals"]["BUY"], 1)
        self.assertEqual(report["performance"]["resolved_pass_fail_n"], 0)

    def test_24_25_26_expected_horizon_display_and_no_guarantee(self):
        dec = {
            "decision_id": "d1",
            "experimental_action": "BUY",
            "final_action": "WAIT",
            "decision_timestamp_utc": "2026-11-09 12:35:00",
            "atr": "2.5",
            "tp_level": "",
            "sl_level": "",
        }
        obs = {
            "symbol": "XAUUSD",
            "bar_close_timestamp_utc": "2026-11-09 12:35:00",
        }
        payload = build_signal_payload(dec, obs)
        content = payload["content"]
        self.assertIn("Expected Horizon: NOT ESTABLISHED", content)
        self.assertIn("Selected Horizon: NOT ESTABLISHED", content)
        self.assertIn("Expected Outcome Checks (PKT):", content)
        self.assertIn(expected_outcome_check_pkt("2026-11-09 12:35:00", "H3"), content)
        self.assertIn("EXPERIMENTAL SHADOW SIGNAL — NOT A LIVE TRADING SIGNAL", content)
        assert_no_guarantee_language(content)
        for phrase in FORBIDDEN_SIGNAL_PHRASES:
            self.assertNotIn(phrase.lower(), content.lower())
        # outcome timeout wording
        out_payload = build_outcome_payload(
            {
                "decision_id": "d1",
                "outcome_event_id": "d1__H3",
                "symbol": "XAUUSD",
                "side": "BUY",
                "horizon_id": "H3",
                "horizon_label": "15M",
                "status": OUTCOME_TIMEOUT,
                "realized_r": "0.05",
                "decision_timestamp_utc": "2026-11-09 12:35:00",
                "outcome_timestamp_utc": "2026-11-09 12:50:00",
            }
        )
        self.assertIn("No TP/SL barrier completed within the selected horizon.", out_payload["content"])
        assert_no_guarantee_language(out_payload["content"])

    def test_27_28_29_30_production_safety(self):
        fake_pred = {
            "experimental_action": "BUY",
            "raw_action": "BUY",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "test",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot_json": "{}",
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = Phase18Store(Path(tmp))
            experience = ExperienceStore(Path(tmp))
            ledger = DeliveryLedger(Path(tmp) / "ledger.jsonl")
            bars = _make_history(30)
            bar = bars[20]
            with patch("phase18.loop.predict_h13c_experimental", return_value=fake_pred):
                result = process_bar(
                    store=store,
                    experience=experience,
                    bar=bar,
                    closes_prefix=[float(b["close"]) for b in bars[:21]],
                    h1_rows=[{"close": 2000.0}] * 30,
                    all_bars=bars,
                    as_of=bar["bar_close_timestamp_utc"],
                    prev_open=bars[19]["bar_open_timestamp_utc"],
                    discord_enabled=True,
                    dry_run_discord=True,
                    ledger=ledger,
                )
            self.assertEqual(result["final_action"], "WAIT")
            self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
            self.assertEqual(CANDIDATE_STATUS, "EXPERIMENTAL")
            self.assertEqual(BROKER_ORDERS, 0)
            self.assertEqual(store.decisions()[0]["final_action"], "WAIT")
            self.assertEqual(len(store.pending_outcomes()), 5)

    def test_31_32_phase16_integrity(self):
        report = verify_protected_hashes()
        self.assertTrue(report["all_ok"], msg=json.dumps(report, indent=2))
        # Explicit 16A/16B keys present and ok
        for key in report["files"]:
            if key.startswith("src/phase16a/") or key.startswith("src/phase16b/"):
                self.assertTrue(report["files"][key]["ok"], key)

    def test_33_phase17_hashes_and_holdout(self):
        report = integrity_report()
        self.assertTrue(report["protected_hashes"]["all_ok"])
        self.assertEqual(HOLDOUT_ACCESSES, 0)
        self.assertEqual(report["holdout_access_count"], 0)
        self.assertEqual(report["broker_order_count"], 0)
        self.assertFalse(report["github_push"])
        # Phase 17 core files frozen
        for rel in (
            "src/phase17/constants.py",
            "src/phase17/loop.py",
            "src/phase17/shadow_messages.py",
            "src/phase17/run_phase17.py",
        ):
            self.assertTrue(report["protected_hashes"]["files"][rel]["ok"], rel)

    def test_34_bounded_loop_idempotent_and_wait_final(self):
        bars = _make_history(35)
        calls = {"n": 0}

        def source():
            calls["n"] += 1
            # Always return same completed set; loop should process max_candles newest then stop offline
            return bars, [{"bar_open_timestamp_utc": "2026-11-09 00:00:00", "close": 2000.0}] * 40, bars[-1]["bar_close_timestamp_utc"]

        fake_pred = {
            "experimental_action": "WAIT",
            "raw_action": "WAIT",
            "final_action": "WAIT",
            "champion_status": CHAMPION_STATUS,
            "experimental_reason": "flat",
            "gate": {"gate_status": "ALLOW"},
            "feature_snapshot_json": "{}",
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("phase18.loop.predict_h13c_experimental", return_value=fake_pred):
                result = run_bounded_multihorizon_loop(
                    max_candles=3,
                    enable_discord=True,
                    dry_run_discord=True,
                    store_root=Path(tmp),
                    bar_source=source,
                )
                result2 = run_bounded_multihorizon_loop(
                    max_candles=3,
                    enable_discord=True,
                    dry_run_discord=True,
                    store_root=Path(tmp),
                    bar_source=source,
                )
            self.assertEqual(result["candles_processed"], 3)
            self.assertEqual(result2["candles_processed"], 0)  # already journaled / last_open advanced
            self.assertFalse(result["any_final_non_wait"])
            self.assertEqual(result["champion_status"], "NO_MODEL")
            self.assertEqual(result["broker_orders"], 0)

    def test_35_daily_report_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Phase18Store(Path(tmp))
            decisions = [
                {
                    "decision_id": "d1",
                    "experimental_action": "BUY",
                    "decision_timestamp_utc": "2026-11-09 10:00:00",
                }
            ]
            # manually inject via store fields
            for d in decisions:
                store.append_decision(
                    {
                        **d,
                        "observation_id": "o1",
                        "source_type": "FORWARD_SHADOW",
                        "symbol": "XAUUSD",
                        "timeframe": "M5",
                        "model_id": "no_model",
                        "model_status": CHAMPION_STATUS,
                        "candidate_id": "H13_C_H1_PULLBACK",
                        "candidate_status": CANDIDATE_STATUS,
                        "raw_action": "BUY",
                        "risk_gate_result": "ALLOW",
                        "final_action": "WAIT",
                        "decision_reason": "t",
                        "feature_snapshot_json": "{}",
                        "selected_horizon": SELECTED_HORIZON_DISPLAY,
                        "outcome_status": "pending_multi_horizon",
                        "signal_bar_open_utc": "2026-11-09 09:55:00",
                        "atr": "",
                        "tp_level": "",
                        "sl_level": "",
                        "is_paper_trade": False,
                        "is_paper_execution": False,
                        "note": "",
                    }
                )
            bundle = build_daily_discord_bundle(
                decisions=store.decisions(),
                outcomes=store.outcomes(),
                date_pkt="2026-11-09",
                generated_at_utc="2026-11-09 18:59:00",
            )
            self.assertEqual(bundle["record"]["report_id"], daily_report_id("2026-11-09"))
            self.assertTrue(store.append_daily_report(bundle["record"]))
            self.assertFalse(store.append_daily_report(bundle["record"]))

    def test_36_h12_matches_twelve_bar_methodology_shape(self):
        bars = _make_history(40)
        signal_idx = 20
        atr = atr_at_signal(bars, signal_idx)
        m = market_arrays_from_bars(bars)
        t12 = simulate_trade_horizon(m, BUY, signal_idx, atr, horizon_bars=12)
        self.assertEqual(t12["horizon_bars"], 12)
        self.assertLessEqual(t12["bars_held"], 12)
        self.assertIn(t12["exit_reason"], {"TP", "SL", "TIME"})


if __name__ == "__main__":
    unittest.main()
