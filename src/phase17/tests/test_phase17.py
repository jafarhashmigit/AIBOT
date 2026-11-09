"""Phase 17 offline tests. No MT5. No real Discord. No holdout."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase17.constants import (
    CHAMPION_STATUS,
    DEFAULT_MAX_CANDLES,
    EXPERIMENTAL_DISCLAIMER,
    SHADOW_BUY_HEADER,
    SHADOW_WAIT_HEADER,
)
from phase17.integrity import verify_protected_hashes
from phase17.loop import process_bar, run_bounded_shadow_loop
from phase17.shadow_messages import build_shadow_payload
from phase16a.storage import Phase16aShadowStore
from phase16b.dedupe import DeliveryLedger


def _bar(open_utc: str, close_utc: str, close: float, *, prev_close: float | None = None) -> dict:
    o = prev_close if prev_close is not None else close
    return {
        "bar_open_timestamp_utc": open_utc,
        "bar_close_timestamp_utc": close_utc,
        "open": o,
        "high": max(o, close) + 0.5,
        "low": min(o, close) - 0.5,
        "close": close,
        "tick_volume": 10,
        "spread": 0.1,
        "complete": True,
        "fabricated": False,
        "source_timezone": "UTC",
        "conversion": "already_utc",
        "source_stamp": open_utc,
        "data_source": "synthetic",
    }


def _synthetic_source(bars: list[dict], h1_rows: list[dict]):
    state = {"calls": 0}

    def source():
        state["calls"] += 1
        # First call returns all bars; later calls return same (no new after last_open)
        return bars, h1_rows, "2026-11-09 13:00:00"

    return source, state


class Phase17Tests(unittest.TestCase):
    def test_01_champion_and_default_bound(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(DEFAULT_MAX_CANDLES, 3)

    def test_02_shadow_message_wait_and_exp_buy(self):
        obs = {"symbol": "XAUUSD", "timeframe": "M5", "bar_close_timestamp_utc": "2026-11-09 12:05:00"}
        wait_payload = build_shadow_payload(
            {
                "decision_id": "d1",
                "experimental_action": "WAIT",
                "final_action": "WAIT",
                "model_status": "NO_MODEL",
                "candidate_status": "EXPERIMENTAL",
            },
            obs,
        )
        self.assertIn(SHADOW_WAIT_HEADER, wait_payload["content"])
        buy_payload = build_shadow_payload(
            {
                "decision_id": "d2",
                "experimental_action": "BUY",
                "final_action": "WAIT",
                "model_status": "NO_MODEL",
                "candidate_status": "EXPERIMENTAL",
            },
            obs,
        )
        self.assertIn(SHADOW_BUY_HEADER, buy_payload["content"])
        self.assertIn(EXPERIMENTAL_DISCLAIMER, buy_payload["content"])
        self.assertIn("final_production_action: WAIT", buy_payload["content"])

    def test_03_journal_before_discord_and_wait_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase16aShadowStore(root)
            ledger = DeliveryLedger(root / "ledger.jsonl")
            order = {"journal": False, "discord": False}

            def transport(url, body, timeout):
                order["discord"] = order["journal"]
                return 204, ""

            # Build enough closes for features (>=20)
            closes = [2000.0 + i * 0.01 for i in range(25)]
            bars = []
            for i in range(25):
                open_t = f"2026-11-09 10:{i:02d}:00" if i < 60 else f"2026-11-09 11:{i-60:02d}:00"
                # Use sequential 5-min stamps simply via minute index in hour 10-11
            # Simpler: fixed last bar only for process_bar unit test
            bar = _bar("2026-11-09 11:00:00", "2026-11-09 11:05:00", closes[-1], prev_close=closes[-2])
            h1 = [{"time": f"2026-11-08 {h:02d}:00:00", "close": 1990.0 + h} for h in range(24)]
            h1 += [{"time": f"2026-11-09 {h:02d}:00:00", "close": 2010.0 + h} for h in range(12)]

            # Monkey-patch append_decision to mark journaled before transport
            orig_dec = store.append_decision

            def wrapped_dec(row):
                orig_dec(row)
                order["journal"] = True

            store.append_decision = wrapped_dec  # type: ignore
            result = process_bar(
                store=store,
                bar=bar,
                closes_prefix=closes,
                h1_rows=h1,
                as_of="2026-11-09 11:05:01",
                prev_open=None,
                discord_enabled=True,
                dry_run_discord=False,
                ledger=ledger,
                transport=transport,
            )
            self.assertTrue(result["journaled"])
            self.assertEqual(result["final_action"], "WAIT")
            self.assertTrue(order["journal"])
            self.assertTrue(order["discord"])  # transport saw journal already true
            self.assertIn(result["experimental_action"], {"BUY", "SELL", "WAIT"})

    def test_04_discord_failure_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase16aShadowStore(root)
            ledger = DeliveryLedger(root / "ledger.jsonl")

            def boom(url, body, timeout):
                return 500, "err"

            closes = [2000.0 + i * 0.01 for i in range(25)]
            bar = _bar("2026-11-09 11:05:00", "2026-11-09 11:10:00", closes[-1], prev_close=closes[-2])
            h1 = [{"time": f"2026-11-09 {h:02d}:00:00", "close": 2000.0 + h} for h in range(20)]
            result = process_bar(
                store=store,
                bar=bar,
                closes_prefix=closes,
                h1_rows=h1,
                as_of="2026-11-09 11:10:01",
                prev_open="2026-11-09 11:00:00",
                discord_enabled=True,
                dry_run_discord=False,
                ledger=ledger,
                transport=boom,
            )
            self.assertTrue(result["journaled"])
            self.assertEqual(result["final_action"], "WAIT")
            self.assertEqual(result["delivery"]["status"], "FAILED_HTTP")
            self.assertFalse(result["delivery"]["changed_decision"])
            self.assertEqual(len(store.decisions()), 1)

    def test_05_duplicate_observation_prevention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            closes = [2000.0 + i * 0.01 for i in range(30)]
            bars = [
                _bar("2026-11-09 11:00:00", "2026-11-09 11:05:00", closes[24], prev_close=closes[23]),
                _bar("2026-11-09 11:05:00", "2026-11-09 11:10:00", closes[25], prev_close=closes[24]),
                _bar("2026-11-09 11:10:00", "2026-11-09 11:15:00", closes[26], prev_close=closes[25]),
            ]
            # Attach closes history by using bar closes from a longer series in source
            hist = []
            for i in range(27):
                minute = i * 5
                h, m = divmod(minute, 60)
                open_t = f"2026-11-09 {10+h:02d}:{m:02d}:00"
                close_t = f"2026-11-09 {10+h:02d}:{m+5:02d}:00" if m + 5 < 60 else f"2026-11-09 {11+h:02d}:{m+5-60:02d}:00"
                # simplify timestamps
            # Use explicit completed history bars for feature window + new bars
            hist_bars = []
            base = 2000.0
            for i in range(22):
                open_t = f"2026-11-09 09:{i:02d}:00"
                close_t = f"2026-11-09 09:{i:02d}:05"  # invalid minutes - use sequential via list only for closes
            # Better approach: feed closes via bars list with unique opens
            all_bars = []
            for i in range(25):
                open_min = i * 5
                oh, om = divmod(open_min, 60)
                ch, cm = divmod(open_min + 5, 60)
                open_t = f"2026-11-09 {8+oh:02d}:{om:02d}:00"
                close_t = f"2026-11-09 {8+ch:02d}:{cm:02d}:00"
                all_bars.append(_bar(open_t, close_t, 2000.0 + i * 0.1, prev_close=2000.0 + max(i - 1, 0) * 0.1))
            h1 = [{"time": f"2026-11-08 {h:02d}:00:00", "close": 1980.0 + h} for h in range(24)]
            source, _ = _synthetic_source(all_bars, h1)
            result = run_bounded_shadow_loop(
                max_candles=3,
                enable_discord=True,
                dry_run_discord=True,
                store_root=root,
                bar_source=source,
            )
            self.assertEqual(result["candles_processed"], 3)
            self.assertFalse(result["lock_remaining"])
            self.assertFalse(result["any_final_non_wait"])
            self.assertFalse(result["mt5_session_started"])
            # Second run should not duplicate same bars
            result2 = run_bounded_shadow_loop(
                max_candles=3,
                enable_discord=True,
                dry_run_discord=True,
                store_root=root,
                bar_source=source,
            )
            self.assertEqual(result2["candles_processed"], 0)

    def test_06_clean_shutdown_lock_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            all_bars = []
            for i in range(25):
                open_min = i * 5
                oh, om = divmod(open_min, 60)
                ch, cm = divmod(open_min + 5, 60)
                open_t = f"2026-11-09 {8+oh:02d}:{om:02d}:00"
                close_t = f"2026-11-09 {8+ch:02d}:{cm:02d}:00"
                all_bars.append(_bar(open_t, close_t, 2000.0 + i * 0.1))
            h1 = [{"time": f"2026-11-08 {h:02d}:00:00", "close": 1980.0 + h} for h in range(24)]
            source, _ = _synthetic_source(all_bars, h1)
            result = run_bounded_shadow_loop(
                max_candles=2,
                dry_run_discord=True,
                store_root=root,
                bar_source=source,
            )
            self.assertEqual(result["status"], "completed")
            self.assertFalse(result["lock_remaining"])
            store = Phase16aShadowStore(root, read_only=True)
            self.assertFalse(store.has_lock())

    def test_07_no_broker_path_and_hashes(self):
        self.assertEqual(verify_protected_hashes()["all_ok"], True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            all_bars = [
                _bar(
                    f"2026-11-09 08:{(i*5)//60:02d}:{(i*5)%60:02d}:00",
                    f"2026-11-09 08:{((i*5)+5)//60:02d}:{((i*5)+5)%60:02d}:00",
                    2000.0 + i,
                )
                for i in range(25)
            ]
            # Fix potential invalid minute formatting for +5 overflow — rebuild cleanly
            all_bars = []
            for i in range(25):
                open_min = i * 5
                close_min = open_min + 5
                oh, om = divmod(open_min, 60)
                ch, cm = divmod(close_min, 60)
                all_bars.append(
                    _bar(
                        f"2026-11-09 {8+oh:02d}:{om:02d}:00",
                        f"2026-11-09 {8+ch:02d}:{cm:02d}:00",
                        2000.0 + i * 0.1,
                    )
                )
            h1 = [{"time": f"2026-11-08 {h:02d}:00:00", "close": 1980.0 + h} for h in range(24)]
            source, _ = _synthetic_source(all_bars, h1)
            result = run_bounded_shadow_loop(
                max_candles=1,
                dry_run_discord=True,
                store_root=root,
                bar_source=source,
            )
            self.assertEqual(result["broker_orders"], 0)
            for row in Phase16aShadowStore(root, read_only=True).decisions():
                self.assertEqual(row["final_action"], "WAIT")
                self.assertEqual(row["is_paper_trade"], "False")


if __name__ == "__main__":
    unittest.main()
