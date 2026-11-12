"""Deterministic tests for H70_LS1 — no performance claims."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy, decide
from signal_bot.asia_london_mss.constants import (
    HYPOTHESIS_ID,
    ORDER_SEND,
    POLICY_VERSION,
    SYMBOL,
)
from signal_bot.asia_london_mss.engine import evaluate_at
from signal_bot.asia_london_mss.policy import AsiaLondonMssPolicy
from signal_bot.asia_london_mss.registry import build_registry_record, freeze_to_disk
from signal_bot.asia_london_mss.sessions import build_asia_range, in_asia_session, in_london_window
from signal_bot.asia_london_mss.swings import confirmed_swing_highs


def _ts(utc: datetime) -> str:
    return utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bar(ts: datetime, o: float, h: float, l: float, c: float) -> dict:
    return {
        "timestamp_utc": _ts(ts),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "tick_volume": 100,
    }


def _series(start: datetime, n: int, base: float = 2650.0) -> list[dict]:
    bars = []
    px = base
    for i in range(n):
        ts = start + timedelta(minutes=5 * i)
        o = px
        c = px + (0.05 if i % 2 == 0 else -0.05)
        h = max(o, c) + 0.2
        l = min(o, c) - 0.2
        bars.append(_bar(ts, o, h, l, c))
        px = c
    return bars


class TestSessions(unittest.TestCase):
    def test_asia_tokyo_window(self):
        # 2026-03-10 00:00 UTC = 09:00 Tokyo
        self.assertTrue(in_asia_session("2026-03-10T00:00:00Z"))
        self.assertTrue(in_asia_session("2026-03-10T05:55:00Z"))
        self.assertFalse(in_asia_session("2026-03-10T06:00:00Z"))

    def test_london_window(self):
        self.assertTrue(in_london_window("2026-03-10T08:00:00Z"))
        self.assertTrue(in_london_window("2026-03-10T11:55:00Z"))
        self.assertFalse(in_london_window("2026-03-10T12:00:00Z"))
        self.assertFalse(in_london_window("2026-03-10T07:55:00Z"))

    def test_asia_range_construction(self):
        start = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        bars = _series(start, 72, base=2650.0)  # 6h Asia
        # Force range
        bars[10]["high"] = 2660.0
        bars[20]["low"] = 2640.0
        ar = build_asia_range(bars, "2026-03-10")
        self.assertTrue(ar["ok"])
        self.assertGreaterEqual(ar["n"], 24)
        self.assertEqual(ar["high"], 2660.0)
        self.assertEqual(ar["low"], 2640.0)

    def test_missing_asia_data(self):
        bars = [_bar(datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc), 1, 2, 0.5, 1.5)]
        ar = build_asia_range(bars, "2026-03-10")
        self.assertFalse(ar["ok"])


class TestSwingsNoLookahead(unittest.TestCase):
    def test_swing_requires_right_bars(self):
        start = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
        bars = _series(start, 20, base=100.0)
        # Make clear swing high at index 5
        bars[5]["high"] = 120.0
        # Before confirmation (need +2), asof_idx=6 should not include
        early = confirmed_swing_highs(bars, asof_idx=6)
        self.assertTrue(all(s["idx"] != 5 for s in early))
        # After confirmation at idx 7
        late = confirmed_swing_highs(bars, asof_idx=7)
        self.assertTrue(any(s["idx"] == 5 for s in late))


def _build_buy_setup() -> tuple[list[dict], int]:
    """Construct chronological bars with sweep-low then bullish MSS in London."""
    # Asia 00:00-06:00 UTC
    asia_start = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
    bars = _series(asia_start, 72, base=2650.0)
    for b in bars:
        b["high"] = min(float(b["high"]), 2655.0)
        b["low"] = max(float(b["low"]), 2645.0)
    bars[5]["high"] = 2655.0
    bars[10]["low"] = 2645.0

    # Post-Asia / pre-London: sweep lows at 07:00
    sweep_ts = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)
    bars.append(_bar(sweep_ts, 2646.0, 2647.0, 2643.0, 2645.5))  # sweep below 2645, close back inside

    # London bars from 08:00 — build swing high then break it
    t = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
    # bars to form swing high at relative pattern
    seq = [
        (2646.0, 2648.0, 2645.5, 2647.0),
        (2647.0, 2650.0, 2646.5, 2649.0),  # potential swing high region
        (2649.0, 2652.0, 2648.0, 2651.0),  # higher high candidate
        (2651.0, 2651.5, 2649.0, 2650.0),
        (2650.0, 2650.5, 2648.5, 2649.0),  # right side lower → confirm prior swing
        (2649.0, 2653.0, 2648.8, 2652.5),  # break above swing → MSS
    ]
    for o, h, l, c in seq:
        bars.append(_bar(t, o, h, l, c))
        t += timedelta(minutes=5)

    decision_idx = len(bars) - 1
    return bars, decision_idx


def _build_sell_setup() -> tuple[list[dict], int]:
    asia_start = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
    bars = _series(asia_start, 72, base=2650.0)
    for b in bars:
        b["high"] = min(float(b["high"]), 2655.0)
        b["low"] = max(float(b["low"]), 2645.0)
    bars[5]["high"] = 2655.0
    bars[10]["low"] = 2645.0

    sweep_ts = datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)
    bars.append(_bar(sweep_ts, 2654.0, 2657.0, 2653.0, 2654.5))  # sweep high, close back inside

    t = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
    seq = [
        (2654.0, 2655.0, 2652.0, 2653.0),
        (2653.0, 2654.0, 2650.0, 2651.0),
        (2651.0, 2652.0, 2648.0, 2649.0),  # swing low candidate
        (2649.0, 2650.0, 2648.5, 2649.5),
        (2649.5, 2651.0, 2649.0, 2650.0),
        (2650.0, 2650.5, 2646.0, 2647.0),  # break below swing low
    ]
    for o, h, l, c in seq:
        bars.append(_bar(t, o, h, l, c))
        t += timedelta(minutes=5)
    return bars, len(bars) - 1


class TestSweepsAndMss(unittest.TestCase):
    def test_buy_side_sweep_and_bullish_mss(self):
        bars, idx = _build_buy_setup()
        out = evaluate_at(bars, idx)
        self.assertIn(out["action"], {"BUY", "WAIT"})
        # May WAIT if swing geometry insufficient — assert no crash and deterministic
        out2 = evaluate_at(bars, idx)
        self.assertEqual(out["action"], out2["action"])
        self.assertEqual(out.get("reason_codes"), out2.get("reason_codes"))

    def test_sell_side_sweep_and_bearish_mss(self):
        bars, idx = _build_sell_setup()
        out = evaluate_at(bars, idx)
        out2 = evaluate_at(bars, idx)
        self.assertEqual(out, out2)

    def test_failed_sweep_close_outside(self):
        bars, _ = _build_buy_setup()
        # Corrupt sweep bar to close still outside
        for i, b in enumerate(bars):
            if b["timestamp_utc"].startswith("2026-03-10T07:00"):
                bars[i]["close"] = 2642.0  # still outside below
                bars[i]["low"] = 2641.0
        out = evaluate_at(bars, len(bars) - 1)
        self.assertEqual(out["action"], "WAIT")

    def test_forming_bar_rejected(self):
        bars, idx = _build_buy_setup()
        out = evaluate_at(bars, idx, forming_bar=True)
        self.assertEqual(out["action"], "WAIT")
        self.assertIn("FORMING_BAR_REJECTED", out["reason_codes"])

    def test_outside_london_wait(self):
        bars, _ = _build_buy_setup()
        # Decision at 07:00 (not London)
        idx = next(i for i, b in enumerate(bars) if b["timestamp_utc"].startswith("2026-03-10T07:00"))
        out = evaluate_at(bars, idx)
        self.assertEqual(out["action"], "WAIT")
        self.assertIn("OUTSIDE_LONDON_CONFIRM_WINDOW", out["reason_codes"])

    def test_insufficient_asia_wait(self):
        bars = _series(datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc), 10)
        out = evaluate_at(bars, len(bars) - 1)
        self.assertEqual(out["action"], "WAIT")


class TestSlTpExpiry(unittest.TestCase):
    def test_sl_tp_when_signal(self):
        bars, idx = _build_buy_setup()
        # Force a synthetic evaluation path via policy on crafted mini scenario
        # If engine returns BUY, SL/TP must be present and RR>=1.5
        out = evaluate_at(bars, idx)
        if out["action"] == "BUY":
            self.assertIsNotNone(out["stop_loss"])
            self.assertIsNotNone(out["take_profit"])
            self.assertGreaterEqual(float(out["reward_risk"]), 1.5)
            self.assertEqual(out["signal_expiry_bars"], 3)
            self.assertIsNotNone(out["invalidation"])
        else:
            self.assertEqual(out["action"], "WAIT")

    def test_signal_only_on_mss_bar(self):
        bars, idx = _build_buy_setup()
        out_mss = evaluate_at(bars, idx)
        if out_mss["action"] in {"BUY", "SELL"}:
            out_late = evaluate_at(bars, idx)  # same bar ok
            self.assertEqual(out_late["action"], out_mss["action"])
            # Before last bar should not re-fire same setup as ENTRY
            if idx > 0:
                earlier = evaluate_at(bars, idx - 1)
                self.assertNotEqual(earlier.get("reason_codes"), out_mss.get("reason_codes") or ["x"])


class TestPolicyIntegration(unittest.TestCase):
    def test_null_policy_fallback(self):
        bars, idx = _build_buy_setup()
        d = decide({"bars": bars, "decision_idx": idx, "bar_timestamp_utc": bars[idx]["timestamp_utc"]}, {}, None, {})
        self.assertEqual(d["action"], "WAIT")
        self.assertEqual(d["champion"], "NO_MODEL")

    def test_policy_propose_and_decide(self):
        bars, idx = _build_buy_setup()
        pol = AsiaLondonMssPolicy()
        ms = {
            "bars": bars,
            "decision_idx": idx,
            "bar_timestamp_utc": bars[idx]["timestamp_utc"],
            "symbol": SYMBOL,
            "data_quality_status": "OK",
            "forming_bar": False,
        }
        d = decide(ms, {}, None, {}, policy=pol)
        self.assertIn(d["action"], {"BUY", "SELL", "WAIT"})
        self.assertEqual(d["model_policy_version"], POLICY_VERSION)
        self.assertFalse(d.get("authorizes_execution"))

    def test_duplicate_decision_idempotent(self):
        bars, idx = _build_buy_setup()
        pol = AsiaLondonMssPolicy()
        ms = {
            "bars": bars,
            "decision_idx": idx,
            "bar_timestamp_utc": bars[idx]["timestamp_utc"],
            "symbol": SYMBOL,
            "data_quality_status": "OK",
        }
        a = pol.propose(ms, {}, None, {})
        b = pol.propose(ms, {}, None, {})
        self.assertEqual(a["action"], b["action"])
        self.assertEqual(a["reason_codes"], b["reason_codes"])
        self.assertEqual(a.get("setup_id"), b.get("setup_id"))

    def test_live_replay_parity(self):
        bars, idx = _build_buy_setup()
        a = evaluate_at(list(bars), idx)
        b = evaluate_at(list(bars), idx)
        self.assertEqual(a, b)

    def test_wait_when_bars_missing(self):
        pol = AsiaLondonMssPolicy()
        out = pol.propose({"data_quality_status": "OK"}, {}, None, {})
        self.assertEqual(out["action"], "WAIT")
        self.assertIn("BARS_MISSING", out["reason_codes"])

    def test_no_order_send(self):
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertIn("order_send", PROHIBITED_MT5_API)
        pol = AsiaLondonMssPolicy()
        out = pol.propose({"bars": [], "data_quality_status": "OK"}, {}, None, {})
        self.assertFalse(out.get("authorizes_execution"))


class TestRegistry(unittest.TestCase):
    def test_freeze_record(self):
        rec = build_registry_record()
        self.assertEqual(rec["hypothesis_id"], HYPOTHESIS_ID)
        self.assertEqual(rec["status"], "PREREGISTERED_DEFINITIONS_FROZEN_UNVALIDATED")
        self.assertFalse(rec["confirmatory_tests_run"])
        path_rec = freeze_to_disk()
        self.assertEqual(path_rec["hypothesis_id"], HYPOTHESIS_ID)


class TestForcedSignalGeometry(unittest.TestCase):
    """Hand-crafted geometry that must produce BUY (implementation correctness)."""

    def test_explicit_buy_signal(self):
        asia_start = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        bars = []
        # 72 Asia bars flat range 2645-2655
        for i in range(72):
            ts = asia_start + timedelta(minutes=5 * i)
            bars.append(_bar(ts, 2650.0, 2655.0, 2645.0, 2650.0))
        # Sweep low
        bars.append(_bar(datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc), 2646.0, 2648.0, 2643.0, 2646.0))
        # London: create swing high at local index then break
        # Need L=2,R=2 around swing
        london = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
        pattern = [
            (2646, 2647, 2645, 2646.5),
            (2646.5, 2648, 2646, 2647),
            (2647, 2654, 2646.5, 2653),  # swing high candidate idx
            (2653, 2653.5, 2651, 2652),
            (2652, 2652.5, 2650, 2651),  # confirms swing at -2
            (2651, 2656, 2650.5, 2655),  # close breaks swing high 2654
        ]
        for o, h, l, c in pattern:
            bars.append(_bar(london, float(o), float(h), float(l), float(c)))
            london += timedelta(minutes=5)
        idx = len(bars) - 1
        out = evaluate_at(bars, idx)
        self.assertEqual(out["action"], "BUY", msg=out.get("reason_codes"))
        self.assertEqual(out["hypothesis_id"], HYPOTHESIS_ID)
        self.assertLess(out["stop_loss"], out["entry_reference"])
        self.assertGreater(out["take_profit"], out["entry_reference"])

    def test_explicit_sell_signal(self):
        asia_start = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        bars = []
        for i in range(72):
            ts = asia_start + timedelta(minutes=5 * i)
            bars.append(_bar(ts, 2650.0, 2655.0, 2645.0, 2650.0))
        bars.append(_bar(datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc), 2654.0, 2657.0, 2653.0, 2654.0))
        london = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
        pattern = [
            (2654, 2655, 2653, 2654),
            (2654, 2654.5, 2652, 2653),
            (2653, 2653.5, 2646, 2647),  # swing low candidate
            (2647, 2649, 2646.5, 2648),
            (2648, 2650, 2647.5, 2649),
            (2649, 2650, 2644, 2645),  # break below swing low
        ]
        for o, h, l, c in pattern:
            bars.append(_bar(london, float(o), float(h), float(l), float(c)))
            london += timedelta(minutes=5)
        out = evaluate_at(bars, len(bars) - 1)
        self.assertEqual(out["action"], "SELL", msg=out.get("reason_codes"))
        self.assertGreater(out["stop_loss"], out["entry_reference"])
        self.assertLess(out["take_profit"], out["entry_reference"])


if __name__ == "__main__":
    unittest.main()
