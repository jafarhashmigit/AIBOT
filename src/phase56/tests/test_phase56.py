"""Phase56 integration tests — integrated lifecycle, not helpers-only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase54.archive_loader import list_archived_m5_days
from phase54.decision import NullPolicy
from phase54.lifecycle import LifecycleEngine
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.candle_registry import CandleRegistry, candle_hash
from phase56.constants import ARCHIVE_ROOT, POLICY_VERSION
from phase56.defect import reproduce_sl_tp_defect
from phase56.lifecycle import IntegratedLifecycleEngine
from phase56.poller import BoundedPoller
from phase56.provider import HistoricalReplayProvider
from phase56.shutdown import graceful_shutdown
from phase56.tests.fixtures import directional_path


class TestDefect(unittest.TestCase):
    def test_phase54_defect_reproduced(self):
        r = reproduce_sl_tp_defect()
        self.assertTrue(r["defect_confirmed"])
        self.assertFalse(r["process_bar_calls_monitor"])
        self.assertTrue(r["process_bar_calls_force_horizon"])


class TestNullPolicyDefault(unittest.TestCase):
    def test_integrated_defaults_to_null(self):
        with tempfile.TemporaryDirectory() as td:
            eng = IntegratedLifecycleEngine(state=AgentState(path=Path(td) / "s.json"))
            self.assertIsInstance(eng.policy, NullPolicy)
            self.assertEqual(eng.policy.version, POLICY_VERSION)
            self.assertIsInstance(eng, LifecycleEngine)


class TestIntegratedSlTp(unittest.TestCase):
    def test_buy_sl_via_integrated_process_bar(self):
        day, m5, h1, by = directional_path(move_after_entry=-5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = IntegratedLifecycleEngine(
                state=AgentState(path=Path(td) / "s.json"),
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"stop_atr_multiple": 0.5, "max_spread_atr": 2.0}),
                immediate_monitor_through_horizon=True,
                use_phase56_stores=True,
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["decision"]["action"], "BUY")
            self.assertTrue(r.get("sl_tp_integrated"))
            self.assertIsNotNone(r.get("closed"))
            self.assertEqual(r["closed"]["exit_fill"], r["closed"]["exit_bid"])
            self.assertIn(r["closed"]["exit_reason"], ("STOP_LOSS", "TAKE_PROFIT", "HORIZON_EXIT"))
            # With -5 move, expect SL
            self.assertEqual(r["closed"]["exit_reason"], "STOP_LOSS")
            self.assertTrue(any(t.get("stage") == "POSITION_MONITORING" for t in r["trace"]))

    def test_buy_tp(self):
        day, m5, h1, by = directional_path(move_after_entry=5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = IntegratedLifecycleEngine(
                state=AgentState(path=Path(td) / "s.json"),
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"stop_atr_multiple": 0.5, "max_spread_atr": 2.0}),
                immediate_monitor_through_horizon=True,
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["closed"]["exit_reason"], "TAKE_PROFIT")
            self.assertEqual(r["closed"]["exit_fill"], r["closed"]["exit_bid"])

    def test_sell_sl_and_tp(self):
        # SELL SL when price rises
        day, m5, h1, by = directional_path(move_after_entry=5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = IntegratedLifecycleEngine(
                state=AgentState(path=Path(td) / "s.json"),
                policy=EngineeringTestPolicy(["SELL"]),
                risk=RiskManager({"stop_atr_multiple": 0.5, "max_spread_atr": 2.0}),
                immediate_monitor_through_horizon=True,
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["decision"]["action"], "SELL")
            self.assertEqual(r["closed"]["exit_reason"], "STOP_LOSS")
            self.assertEqual(r["closed"]["exit_fill"], r["closed"]["exit_ask"])
        # SELL TP when price falls
        day, m5, h1, by = directional_path(move_after_entry=-5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = IntegratedLifecycleEngine(
                state=AgentState(path=Path(td) / "s.json"),
                policy=EngineeringTestPolicy(["SELL"]),
                risk=RiskManager({"stop_atr_multiple": 0.5, "max_spread_atr": 2.0}),
                immediate_monitor_through_horizon=True,
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["closed"]["exit_reason"], "TAKE_PROFIT")

    def test_same_bar_sl_before_tp_priority(self):
        """Frozen priority: within a tick loop SL is evaluated before TP for BUY."""
        from phase54.paper_exec import monitor_and_maybe_exit

        day, m5, h1, by = directional_path(move_after_entry=0.0)
        # Craft entry bar ticks: first tick hits both conceptually — bid below SL
        entry_idx = 49
        entry_ts = str(m5[entry_idx]["timestamp_utc"])
        entry_ask = 2000.05
        pos = {
            "position_id": "p",
            "side": "BUY",
            "status": "OPEN",
            "entry_idx": entry_idx,
            "entry_fill": entry_ask,
            "entry_bid": 2000.0,
            "entry_ask": entry_ask,
            "stop_loss": entry_ask - 0.01,
            "take_profit": entry_ask + 0.01,
            "atr_at_entry": 1.0,
            "audit": [],
        }
        # First tick: bid at SL (and would also be far from TP)
        by[entry_ts] = [
            {"epoch_ms": 1, "timestamp_utc": entry_ts, "bid": entry_ask - 0.02, "ask": entry_ask - 0.01},
            {"epoch_ms": 2, "timestamp_utc": entry_ts, "bid": entry_ask + 0.05, "ask": entry_ask + 0.06},
        ]
        closed = monitor_and_maybe_exit(pos, m5=m5, ticks_by_bar=by, current_idx=entry_idx, horizon_bars=12)
        self.assertEqual(closed["exit_reason"], "STOP_LOSS")


class TestCandleIdempotency(unittest.TestCase):
    def test_duplicate_and_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            reg = CandleRegistry(path=Path(td) / "c.json")
            bar = {"timestamp_utc": "2099-01-01 10:00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5}
            g1 = reg.evaluate(bar, policy_version="v1")
            self.assertTrue(g1["accept"])
            reg.commit(bar, policy_version="v1")
            g2 = reg.evaluate(bar, policy_version="v1")
            self.assertEqual(g2["reason"], "DUPLICATE_CANDLE_TIMESTAMP")
            bad = {**bar, "close": 9.9}
            g3 = reg.evaluate(bad, policy_version="v1")
            self.assertEqual(g3["reason"], "CONFLICTING_DUPLICATE_HASH")


class TestRecoveryAndShutdown(unittest.TestCase):
    def test_restart_open_then_monitor(self):
        day, m5, h1, by = directional_path(move_after_entry=0.0)
        with tempfile.TemporaryDirectory() as td:
            sp = Path(td) / "s.json"
            eng = IntegratedLifecycleEngine(
                state=AgentState(path=sp),
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0}),
                immediate_monitor_through_horizon=False,
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["decision"]["action"], "BUY")
            self.assertIsNone(r.get("closed"))
            self.assertEqual(len(eng.risk.open_positions), 1)
            graceful_shutdown(eng, reason="TEST")
            # restart
            eng2 = IntegratedLifecycleEngine(
                state=AgentState(path=sp),
                policy=NullPolicy(),
                immediate_monitor_through_horizon=False,
            )
            self.assertEqual(len(eng2.risk.open_positions), 1)
            # force SL by rewriting stop and crashing price on later bar
            pid = next(iter(eng2.risk.open_positions))
            pos = eng2.risk.open_positions[pid]
            pos["stop_loss"] = float(pos["entry_fill"]) + 100  # unreachable SL for BUY... use TP instead
            pos["take_profit"] = float(pos["entry_fill"]) - 0.01  # hit immediately on next monitor with flat/down
            # actually for BUY TP needs bid >= tp; set tp below and move — use SL below entry
            pos["stop_loss"] = float(pos["entry_fill"]) - 0.01
            pos["take_profit"] = float(pos["entry_fill"]) + 100
            eng2.risk.open_positions[pid] = pos
            # drop prices after entry
            for j in range(49, 55):
                ts = str(m5[j]["timestamp_utc"])
                fill = float(pos["entry_fill"]) - 1.0
                by[ts] = [{"epoch_ms": j, "timestamp_utc": ts, "bid": fill, "ask": fill + 0.1}]
            closed = eng2.monitor_open_positions(day=day, m5=m5, ticks_by_bar=by, current_idx=54)
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0]["exit_reason"], "STOP_LOSS")
            # idempotent decision
            again = eng2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertTrue(again.get("skipped"))


class TestPollerBounds(unittest.TestCase):
    def test_bounded_stop(self):
        days = list_archived_m5_days(ARCHIVE_ROOT)[:1]
        if not days:
            self.skipTest("no archive")
        with tempfile.TemporaryDirectory() as td:
            eng = IntegratedLifecycleEngine(
                state=AgentState(path=Path(td) / "s.json"),
                policy=NullPolicy(),
                immediate_monitor_through_horizon=False,
            )
            # fresh candle registry path
            eng.observer.registry.path = Path(td) / "candles.json"
            eng.observer.registry.data = {"by_ts": {}, "last_ts": None, "last_hash": None, "rejected": []}
            provider = HistoricalReplayProvider(days=days, stride=12, max_candles=5)
            poller = BoundedPoller(eng, provider, config={"max_candles": 5, "max_iterations": 100, "max_wall_seconds": 60})
            meta = poller.run()
            self.assertIn(meta["stop_reason"], ("max_candles", "COMPLETED"))
            self.assertLessEqual(meta["candles"], 5)
            self.assertGreater(meta["candles"], 0)
            self.assertFalse(meta["live_mt5"])
            self.assertFalse(meta["auto_started"])


class TestRiskAndStale(unittest.TestCase):
    def test_risk_blocks_entry(self):
        day, m5, h1, by = directional_path()
        with tempfile.TemporaryDirectory() as td:
            risk = RiskManager()
            risk.circuit_open = True
            risk.safety_state = "CIRCUIT_BREAKER_WAIT"
            eng = IntegratedLifecycleEngine(
                state=AgentState(path=Path(td) / "s.json"),
                policy=EngineeringTestPolicy(["BUY"]),
                risk=risk,
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["decision"]["action"], "WAIT")
            self.assertIsNone(r.get("closed"))

    def test_feed_unsafe_forces_reject(self):
        day, m5, h1, by = directional_path()
        with tempfile.TemporaryDirectory() as td:
            eng = IntegratedLifecycleEngine(state=AgentState(path=Path(td) / "s.json"))
            eng.feed_safety.mark_feed_stale("TEST_STALE")
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertTrue(r.get("rejected"))
            self.assertIn("FEED_UNSAFE", r.get("reason_codes") or [])


if __name__ == "__main__":
    unittest.main()
