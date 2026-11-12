"""Independent Phase57 reliability tests — do not merely echo Phase56 assertions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase54.decision import NullPolicy
from phase54.paper_exec import monitor_and_maybe_exit
from phase54.risk import RiskManager
from phase55.engineering_policy import EngineeringTestPolicy
from phase56.lifecycle import IntegratedLifecycleEngine
from phase57.adapter import make_engine
from phase57.constants import EXPECTED_NULL_POLICY
from phase57.crash_inject import STAGES, run_crash_stage
from phase57.execution_cases import run_execution_integrity
from phase57.fixtures import clean_bundle, conflicting_duplicate_bar
from phase57.invariants import (
    check_buy_sell_prices,
    check_independent_recompute,
    check_null_policy_default,
    check_sl_first_same_bar,
)
from phase57.stress import run_stress
from phase57.suite import choose_verdict, run_lifecycle_integrity


class TestNullPolicyUntouched(unittest.TestCase):
    def test_default_is_null_policy(self):
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(state_path=Path(td) / "s.json", registry_path=Path(td) / "c.json")
            r = check_null_policy_default(eng)
            self.assertTrue(r["ok"])
            self.assertEqual(eng.policy.version, EXPECTED_NULL_POLICY)
            self.assertIsInstance(eng.policy, NullPolicy)
            self.assertIsInstance(eng, IntegratedLifecycleEngine)


class TestLifecycleIndependents(unittest.TestCase):
    def test_buy_exit_uses_bid_not_ask(self):
        day, m5, h1, by = clean_bundle(move_after_entry=-5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(
                state_path=Path(td) / "s.json",
                registry_path=Path(td) / "c.json",
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
                hist_root=Path(td) / "h",
                shadow_root=Path(td) / "sh",
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertIsNotNone(r.get("closed"))
            self.assertEqual(r["closed"]["exit_fill"], r["closed"]["exit_bid"])
            self.assertNotEqual(r["closed"]["exit_bid"], r["closed"]["exit_ask"])
            chk = check_buy_sell_prices([r["closed"]])
            self.assertTrue(chk["ok"])

    def test_sell_exit_uses_ask(self):
        day, m5, h1, by = clean_bundle(move_after_entry=5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(
                state_path=Path(td) / "s.json",
                registry_path=Path(td) / "c.json",
                policy=EngineeringTestPolicy(["SELL"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
                hist_root=Path(td) / "h",
                shadow_root=Path(td) / "sh",
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["closed"]["exit_fill"], r["closed"]["exit_ask"])

    def test_duplicate_candle_no_second_decision(self):
        day, m5, h1, by = clean_bundle()
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(
                state_path=Path(td) / "s.json",
                registry_path=Path(td) / "c.json",
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
                immediate_monitor_through_horizon=True,
                hist_root=Path(td) / "h",
                shadow_root=Path(td) / "sh",
            )
            r1 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            r2 = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertFalse(r1.get("skipped"))
            self.assertTrue(r2.get("skipped"))
            keys = eng.state.data.get("processed_decision_keys") or []
            self.assertEqual(keys.count(f"{day}:48"), 1)

    def test_sl_first_independent_of_engine_process_bar(self):
        day, m5, h1, by = clean_bundle()
        r = check_sl_first_same_bar(m5, by, 49)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["exit_reason"], "STOP_LOSS")

    def test_independent_recompute_matches_engine(self):
        day, m5, h1, by = clean_bundle(move_after_entry=-5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(
                state_path=Path(td) / "s.json",
                registry_path=Path(td) / "c.json",
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
                hist_root=Path(td) / "h",
                shadow_root=Path(td) / "sh",
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            cmp_ = check_independent_recompute(r["closed"], m5, by)
            self.assertTrue(cmp_["ok"], cmp_)

    def test_closed_cannot_close_twice(self):
        day, m5, h1, by = clean_bundle(move_after_entry=-5.0)
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(
                state_path=Path(td) / "s.json",
                registry_path=Path(td) / "c.json",
                policy=EngineeringTestPolicy(["BUY"]),
                risk=RiskManager({"max_spread_atr": 2.0, "stop_atr_multiple": 0.5}),
                hist_root=Path(td) / "h",
                shadow_root=Path(td) / "sh",
            )
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            closed = r["closed"]
            pid = closed["position_id"]
            # Force monitor again with same closed id registered
            eng.risk.open_positions[pid] = {**closed, "status": "OPEN"}
            again = eng.monitor_open_positions(day=day, m5=m5, ticks_by_bar=by, current_idx=60)
            ids = eng.state.data.get("closed_position_ids") or []
            self.assertEqual(ids.count(pid), 1)
            self.assertEqual(again, [])


class TestCrashRecovery(unittest.TestCase):
    def test_all_crash_stages_no_duplicate_entry(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            for stage in STAGES:
                row = run_crash_stage(stage, work_dir=work)
                self.assertFalse(row.get("duplicate_open_after_restart"), stage)
                self.assertFalse(row.get("double_close"), stage)
                self.assertTrue(row.get("idempotent_reprocess"), stage)

    def test_outcome_gap_does_not_double_close(self):
        with tempfile.TemporaryDirectory() as td:
            row = run_crash_stage("after_exit_before_outcome", work_dir=Path(td))
            self.assertTrue(row.get("outcome_gap_injected"))
            self.assertTrue(row.get("lost_outcome_after_gap"))
            self.assertFalse(row.get("double_close"))
            self.assertFalse(row.get("experience_rebuild_supported"))


class TestExecutionAndDQ(unittest.TestCase):
    def test_execution_integrity_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_execution_integrity(Path(td))
            self.assertTrue(out["cases"]["zero_negative_ohlc"]["ok"])
            self.assertTrue(out["cases"]["crossed_market"]["ok"])
            self.assertTrue(out["cases"]["invalid_stop"]["ok"])
            self.assertTrue(out["cases"]["conflicting_hash"]["ok"])
            self.assertTrue(out["cases"]["out_of_order"]["ok"])
            self.assertTrue(out["cases"]["stale_blocks_entry"]["ok"])
            self.assertTrue(out["cases"]["daily_loss_blocks_entry"]["ok"])

    def test_conflicting_hash_helper(self):
        day, m5, h1, by = clean_bundle()
        bar = m5[48]
        conf = conflicting_duplicate_bar(bar)
        self.assertNotEqual(bar["close"], conf["close"])


class TestStressAndDeterminism(unittest.TestCase):
    def test_stress_ok(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_stress(Path(td))
            self.assertTrue(out["evidence"]["deterministic"]["ok"], out["evidence"]["deterministic"])
            self.assertTrue(out["evidence"]["duplicates"]["ok"], out["evidence"]["duplicates"])
            self.assertTrue(out["evidence"]["multi_restart"]["ok"], out["evidence"]["multi_restart"])

    def test_lifecycle_suite_block(self):
        with tempfile.TemporaryDirectory() as td:
            out = run_lifecycle_integrity(Path(td))
            self.assertTrue(out["ok"], out["invariants"])


class TestVerdictRules(unittest.TestCase):
    def test_failed_on_hard_invariant(self):
        v, _ = choose_verdict(
            {
                "critical_ok": False,
                "critical_invariants": {
                    "null_policy_default": {"ok": False},
                    "once_per_accepted_observation": {"ok": True},
                },
            }
        )
        self.assertEqual(v, "AUTONOMOUS_RELIABILITY_FAILED")

    def test_validated_requires_all(self):
        from phase57.constants import CRITICAL_INVARIANTS

        crit = {k: {"ok": True} for k in CRITICAL_INVARIANTS}
        v, _ = choose_verdict({"critical_ok": True, "critical_invariants": crit, "failures": []})
        self.assertEqual(v, "AUTONOMOUS_RELIABILITY_VALIDATED")

    def test_high_gap_forces_partial(self):
        from phase57.constants import CRITICAL_INVARIANTS

        crit = {k: {"ok": True} for k in CRITICAL_INVARIANTS}
        v, reason = choose_verdict(
            {
                "critical_ok": True,
                "critical_invariants": crit,
                "failures": [{"id": "outcome_gap:after_exit_before_outcome", "severity": "HIGH"}],
            }
        )
        self.assertEqual(v, "AUTONOMOUS_RELIABILITY_PARTIAL")
        self.assertIn("HIGH", reason)


class TestNoLookaheadProperty(unittest.TestCase):
    def test_monitor_does_not_read_beyond_current_idx(self):
        """Property: exit cannot use ticks after current_idx."""
        day, m5, h1, by = clean_bundle(move_after_entry=-5.0)
        entry_idx = 49
        entry_ask = float(by[str(m5[entry_idx]["timestamp_utc"])][0]["ask"])
        pos = {
            "position_id": "p",
            "side": "BUY",
            "status": "OPEN",
            "entry_idx": entry_idx,
            "entry_fill": entry_ask,
            "entry_bid": entry_ask - 0.01,
            "entry_ask": entry_ask,
            "stop_loss": entry_ask - 0.5,
            "take_profit": entry_ask + 100,
            "atr_at_entry": 1.0,
            "audit": [],
        }
        # At entry bar only — SL not yet hit (move starts at 50)
        closed_early = monitor_and_maybe_exit(pos, m5=m5, ticks_by_bar=by, current_idx=entry_idx, horizon_bars=12)
        self.assertIsNone(closed_early)
        closed_later = monitor_and_maybe_exit(pos, m5=m5, ticks_by_bar=by, current_idx=entry_idx + 2, horizon_bars=12)
        self.assertIsNotNone(closed_later)
        self.assertLessEqual(closed_later["exit_idx"], entry_idx + 2)


if __name__ == "__main__":
    unittest.main()
