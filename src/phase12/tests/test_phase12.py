"""Twenty-three required Phase 12 tests. Synthetic fixtures. No MT5."""

from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path

from phase6.risk_gate import RiskGate
from phase12.bar_validator import BarError, require_completed, validate_ohlc
from phase12.decision_recorder import apply_frozen_gate, propose_action, record_shadow_decision
from phase12.market_data_reader import SyntheticReader, broker_order_calls, mt5_connections
from phase12.observation_builder import build_observation
from phase12.outcome_observer import observe_outcome
from phase12.session_manager import SessionManager
from phase12.tests.fixtures import LABEL, SYNTHETIC, bar_at, continuous_bars, created_at, replay_as_of
from phase12.timestamp_normalizer import TimestampError, normalize
from phase12.validation import ShadowError, assert_no_broker_in_text, snapshot_protected


class Phase12Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SYNTHETIC)
        self.assertIn("SYNTHETIC", LABEL)

    def _mgr(self) -> SessionManager:
        tmp = Path(tempfile.mkdtemp())
        return SessionManager(tmp)

    def test_01_valid_completed_m5_bar_acceptance(self):
        reader = SyntheticReader(continuous_bars(2))
        bars = reader.poll_completed(as_of_utc=replay_as_of(), previous_open_utc=None)
        self.assertEqual(len(bars), 2)
        validate_ohlc(bars[0])

    def test_02_incomplete_candle_rejection(self):
        bar = bar_at(0, complete=False)
        built = {
            "bar_close_timestamp_utc": bar["bar_close"],
            "complete": False,
        }
        with self.assertRaises(BarError):
            require_completed(built, as_of_utc=replay_as_of())

    def test_03_invalid_ohlc_rejection(self):
        with self.assertRaises(BarError):
            validate_ohlc({"open": 10, "high": 9, "low": 8, "close": 9.5, "tick_volume": 1})

    def test_04_duplicate_timestamp_rejection(self):
        mgr = self._mgr()
        mgr.start(session_id="t", mode="offline_synthetic")
        mgr.ingest_synthetic(continuous_bars(2), as_of_utc=replay_as_of(), created_at_utc=created_at())
        again = mgr.ingest_synthetic(continuous_bars(2), as_of_utc=replay_as_of(), created_at_utc=created_at())
        self.assertEqual(again["new_observations"], 0)
        self.assertEqual(again["duplicate_skipped"], 2)

    def test_05_utc_timestamp_normalization(self):
        out = normalize("2026-11-02 10:00:00", "UTC")
        self.assertEqual(out["utc"], "2026-11-02 10:00:00")
        self.assertEqual(out["source_timezone"], "UTC")

    def test_06_unknown_timezone_rejection(self):
        with self.assertRaises(TimestampError):
            normalize("2026-11-02 10:00:00", None)
        with self.assertRaises(TimestampError):
            normalize("2026-11-02 10:00:00", "unknown")

    def test_07_dst_boundary_handling(self):
        winter = normalize("2026-03-27 12:00:00", "Europe/Athens")
        summer = normalize("2026-03-30 12:00:00", "Europe/Athens")
        self.assertEqual(winter["utc_offset_hours"], 2)
        self.assertEqual(summer["utc_offset_hours"], 3)
        with self.assertRaises(TimestampError):
            normalize("2026-03-29 03:30:00", "Europe/Athens")
        with self.assertRaises(TimestampError):
            normalize("2026-10-25 03:30:00", "Europe/Athens")

    def test_08_gap_detection(self):
        bars = [bar_at(0), bar_at(3)]
        reader = SyntheticReader(bars)
        out = reader.poll_completed(as_of_utc=replay_as_of(), previous_open_utc=None)
        self.assertEqual(out[1]["gap_status"], "gap")

    def test_09_no_fabricated_bars(self):
        reader = SyntheticReader([bar_at(0, fabricated=True, stop_on_error=True)])
        with self.assertRaises(Exception):
            reader.poll_completed(as_of_utc=replay_as_of(), previous_open_utc=None)

    def test_10_no_approved_model_wait(self):
        proposal = propose_action()
        self.assertEqual(proposal["model_status"], "NO_MODEL")
        self.assertEqual(proposal["raw_action"], "WAIT")
        self.assertEqual(proposal["decision_reason"], "NO_APPROVED_MODEL")
        with self.assertRaises(ShadowError):
            propose_action(champion_id="phase9_experience_ridge_v1")

    def test_11_riskgate_remains_unchanged(self):
        gate = RiskGate()
        self.assertTrue(gate.wait_only)
        self.assertEqual(gate.champion_id, "no_model")
        snap = snapshot_protected()
        self.assertTrue(snap["src/phase6/risk_gate.py"]["unchanged"])
        status, final = apply_frozen_gate("WAIT")
        self.assertEqual((status, final), ("ALLOW", "WAIT"))
        self.assertEqual(apply_frozen_gate("BUY"), ("BLOCK", "WAIT"))

    def test_12_wait_is_not_a_paper_trade(self):
        obs = build_observation(
            SyntheticReader(continuous_bars(1)).poll_completed(
                as_of_utc=replay_as_of(), previous_open_utc=None
            )[0],
            created_at_utc=created_at(),
        )
        dec = record_shadow_decision(obs)
        self.assertEqual(dec["final_action"], "WAIT")
        self.assertFalse(dec["is_paper_trade"])

    def test_13_shadow_decision_is_not_a_paper_execution(self):
        obs = build_observation(
            SyntheticReader(continuous_bars(1)).poll_completed(
                as_of_utc=replay_as_of(), previous_open_utc=None
            )[0],
            created_at_utc=created_at(),
        )
        dec = record_shadow_decision(obs)
        self.assertFalse(dec["is_paper_execution"])
        self.assertEqual(dec["source_type"], "FORWARD_SHADOW")
        self.assertNotEqual(dec["source_type"], "AGENT_PAPER")

    def test_14_future_outcome_exclusion(self):
        mgr = self._mgr()
        mgr.start(session_id="t", mode="offline_synthetic")
        mgr.ingest_synthetic(continuous_bars(2), as_of_utc="2026-11-02 10:12:00", created_at_utc=created_at())
        pending = [o for o in mgr.store.outcomes() if o["outcome_status"] == "pending"]
        self.assertTrue(pending)

    def test_15_equal_timestamp_exclusion(self):
        dec = {
            "decision_id": "shadow:x",
            "decision_timestamp_utc": "2026-11-02 10:05:00",
        }
        result = observe_outcome(dec, [], as_of_utc="2026-11-02 11:05:00")
        self.assertEqual(result["outcome_status"], "pending")

    def test_16_incomplete_outcome_remains_pending(self):
        mgr = self._mgr()
        mgr.start(session_id="t", mode="offline_synthetic")
        mgr.ingest_synthetic(continuous_bars(5), as_of_utc=replay_as_of(), created_at_utc=created_at())
        statuses = {o["outcome_status"] for o in mgr.store.outcomes()}
        self.assertIn("pending", statuses)

    def test_17_gap_crossing_outcome_exclusion(self):
        bars = [bar_at(i) for i in range(3)] + [bar_at(i) for i in range(6, 20)]
        mgr = self._mgr()
        mgr.start(session_id="t", mode="offline_synthetic")
        mgr.ingest_synthetic(bars, as_of_utc=replay_as_of(), created_at_utc=created_at())
        excluded = [o for o in mgr.store.outcomes() if o["outcome_status"] == "excluded_gap"]
        self.assertTrue(excluded)

    def test_18_restart_does_not_duplicate_records(self):
        tmp = Path(tempfile.mkdtemp())
        a = SessionManager(tmp)
        a.start(session_id="t", mode="offline_synthetic")
        a.ingest_synthetic(continuous_bars(3), as_of_utc=replay_as_of(), created_at_utc=created_at())
        a.stop()
        b = SessionManager(tmp)
        b.start(session_id="t2", mode="offline_synthetic")
        result = b.ingest_synthetic(continuous_bars(3), as_of_utc=replay_as_of(), created_at_utc=created_at())
        self.assertEqual(result["new_observations"], 0)
        self.assertEqual(len(b.store.observations()), 3)

    def test_19_session_stop_works(self):
        mgr = self._mgr()
        mgr.start(session_id="t", mode="offline_synthetic")
        self.assertTrue(mgr.status()["running"])
        mgr.stop()
        self.assertFalse(mgr.status()["running"])

    def test_20_no_concurrent_sessions(self):
        mgr = self._mgr()
        mgr.start(session_id="t", mode="offline_synthetic")
        with self.assertRaises(ShadowError):
            mgr.start(session_id="t2", mode="offline_synthetic")

    def test_21_no_broker_order_function_calls(self):
        self.assertEqual(broker_order_calls(), 0)
        self.assertEqual(mt5_connections(), 0)
        self.assertNotIn("MetaTrader5", sys.modules)
        from phase12 import market_data_reader, mt5_readonly
        assert_no_broker_in_text(inspect.getsource(market_data_reader))
        assert_no_broker_in_text(inspect.getsource(mt5_readonly))

    def test_22_no_phase_1_11_artifact_changes(self):
        snap = snapshot_protected()
        self.assertTrue(all(v["unchanged"] for v in snap.values()))

    def test_23_deterministic_offline_fixture_replay(self):
        a = self._mgr()
        b = self._mgr()
        a.start(session_id="a", mode="offline_synthetic")
        b.start(session_id="b", mode="offline_synthetic")
        ra = a.ingest_synthetic(continuous_bars(8), as_of_utc=replay_as_of(), created_at_utc=created_at())
        rb = b.ingest_synthetic(continuous_bars(8), as_of_utc=replay_as_of(), created_at_utc=created_at())
        self.assertEqual(ra["new_observations"], rb["new_observations"])
        self.assertEqual(
            [d["final_action"] for d in a.store.decisions()],
            [d["final_action"] for d in b.store.decisions()],
        )


if __name__ == "__main__":
    unittest.main()
