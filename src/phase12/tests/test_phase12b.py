"""Phase 12B preflight tests. Mocks and synthetic fixtures only. No MT5 connection."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import sys
import tempfile
import unittest
from pathlib import Path

from phase3.nplib import sha256_file
from phase6.information_boundary import InformationBoundaryError
from phase6.risk_gate import RiskGate
from phase6.tests.factories import observation
from phase12.decision_recorder import apply_frozen_gate, propose_action, record_shadow_decision
from phase12.market_data_reader import SyntheticReader, broker_order_calls, mt5_connections
from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API, audit_phase12_tree, audit_source
from phase12.observation_builder import build_observation
from phase12.parity_audit import POST_CUTOFF, PRE_CUTOFF, phase6_evaluate_final, run_parity_audit
from phase12.session_manager import SessionManager
from phase12.storage import ShadowStore
from phase12.tests.fixtures import continuous_bars, created_at, replay_as_of
from phase12.validation import PROJECT_ROOT, SRC_DIR, ShadowError, snapshot_protected

PHASE12_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = PHASE12_ROOT / "mt5_readonly.py"
HISTORICAL_DATASETS = [
    PROJECT_ROOT / "src/data/xauusd_m5_labeled.csv",
    PROJECT_ROOT / "src/data/m5_side_outcomes.csv",
    PROJECT_ROOT / "src/data/phase2_oos_predictions.csv",
    PROJECT_ROOT / "src/data/phase8_replay_log.csv",
    PROJECT_ROOT / "src/data/phase9_replay_log.csv",
    PROJECT_ROOT / "src/data/xauusd_m5_train.csv",
]
PAPER_ARTIFACTS = [
    PROJECT_ROOT / "src/phase10/paper_store.py",
    PROJECT_ROOT / "src/phase10/run_phase10.py",
]


def _hashes(paths) -> dict:
    return {str(p): sha256_file(p) for p in paths if p.exists()}


class Phase12BTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertNotIn("MetaTrader5", sys.modules)

    def _mgr(self) -> SessionManager:
        return SessionManager(Path(tempfile.mkdtemp()))

    def test_01_mt5_adapter_import_has_no_connection_side_effect(self):
        self.assertNotIn("MetaTrader5", sys.modules)
        import phase12.mt5_readonly as adapter
        importlib.reload(adapter)
        self.assertNotIn("MetaTrader5", sys.modules)
        self.assertEqual(mt5_connections(), 0)
        self.assertEqual(broker_order_calls(), 0)
        self.assertFalse(hasattr(adapter, "mt5"))

    def test_02_no_prohibited_trading_api_in_adapter_call_graph(self):
        row = audit_source(ADAPTER)
        self.assertEqual(row["prohibited_found"], [])
        self.assertFalse(row["module_level_mt5_import"])
        self.assertFalse(row["import_time_initialize"])
        self.assertFalse(row["has_thread"])
        self.assertFalse(row["has_reconnect_loop"])
        tree = audit_phase12_tree(PHASE12_ROOT)
        self.assertEqual(tree["prohibited_any"], [])
        self.assertEqual(tree["api_outside_adapter"], [])

    def test_03_mt5_allowlist_enforcement(self):
        row = audit_source(ADAPTER)
        self.assertTrue(row["passed"])
        for name in row["permitted_used"]:
            self.assertIn(name, PERMITTED_MT5_API)
        for banned in PROHIBITED_MT5_API:
            self.assertNotIn(banned, row["permitted_used"])
        self.assertTrue(audit_phase12_tree(PHASE12_ROOT)["passed"])

    def test_04_phase6_wait_only_parity(self):
        audit = run_parity_audit()
        self.assertTrue(audit["pre_cutoff"]["all_match"])
        self.assertTrue(audit["pre_cutoff"]["all_final_wait"])
        self.assertTrue(audit["post_cutoff"]["observation_construction_raises"])
        self.assertEqual(audit["forward_evaluate_parity"], "INCOMPLETE")
        self.assertFalse(audit["phase6_evaluate_supports_forward_observations"])
        self.assertEqual(audit["overall"], "INCOMPLETE")
        with self.assertRaises(InformationBoundaryError):
            observation(timestamp=POST_CUTOFF)

    def test_05_buy_proposal_blocked(self):
        p6 = phase6_evaluate_final("BUY", PRE_CUTOFF)
        p12 = apply_frozen_gate("BUY")
        self.assertEqual(p6, ("BLOCK", "WAIT"))
        self.assertEqual(p12, ("BLOCK", "WAIT"))

    def test_06_sell_proposal_blocked(self):
        p6 = phase6_evaluate_final("SELL", PRE_CUTOFF)
        p12 = apply_frozen_gate("SELL")
        self.assertEqual(p6, ("BLOCK", "WAIT"))
        self.assertEqual(p12, ("BLOCK", "WAIT"))

    def test_07_wait_remains_wait(self):
        p6 = phase6_evaluate_final("WAIT", PRE_CUTOFF)
        p12 = apply_frozen_gate("WAIT")
        self.assertEqual(p6, ("ALLOW", "WAIT"))
        self.assertEqual(p12, ("ALLOW", "WAIT"))

    def test_08_missing_model_remains_wait(self):
        proposal = propose_action()
        self.assertEqual(proposal["model_status"], "NO_MODEL")
        self.assertEqual(proposal["raw_action"], "WAIT")
        obs = build_observation(
            SyntheticReader(continuous_bars(1)).poll_completed(
                as_of_utc=replay_as_of(), previous_open_utc=None
            )[0],
            created_at_utc=created_at(),
        )
        dec = record_shadow_decision(obs)
        self.assertEqual(dec["final_action"], "WAIT")

    def test_09_unknown_model_cannot_bypass_the_gate(self):
        with self.assertRaises(ShadowError):
            propose_action(champion_id="unknown_model_xyz")
        gate = RiskGate()
        self.assertEqual(gate.champion_id, "no_model")
        self.assertTrue(gate.wait_only)
        self.assertEqual(apply_frozen_gate("BUY")[1], "WAIT")

    def test_10_post_cutoff_observations_remain_in_phase12_only(self):
        calls = []
        original = RiskGate.evaluate

        def wrapped(self, observation, prediction, decision_context):
            calls.append(observation.timestamp)
            return original(self, observation, prediction, decision_context)

        RiskGate.evaluate = wrapped
        try:
            mgr = self._mgr()
            mgr.start(session_id="iso", mode="offline_synthetic")
            mgr.ingest_synthetic(continuous_bars(2), as_of_utc=replay_as_of(), created_at_utc=created_at())
            self.assertEqual(calls, [])
            for row in mgr.store.observations():
                self.assertEqual(row["source_type"], "FORWARD_SHADOW")
                self.assertGreater(row["bar_open_timestamp_utc"], "2026-09-29 18:50:00")
        finally:
            RiskGate.evaluate = original
        with self.assertRaises(InformationBoundaryError):
            observation(timestamp=POST_CUTOFF)

    def test_11_forward_source_type_is_preserved(self):
        mgr = self._mgr()
        mgr.start(session_id="src", mode="offline_synthetic")
        mgr.ingest_synthetic(continuous_bars(1), as_of_utc=replay_as_of(), created_at_utc=created_at())
        obs = mgr.store.observations()[0]
        dec = mgr.store.decisions()[0]
        self.assertEqual(obs["source_type"], "FORWARD_SHADOW")
        self.assertEqual(dec["source_type"], "FORWARD_SHADOW")
        self.assertNotEqual(dec["source_type"], "AGENT_PAPER")
        self.assertNotEqual(dec["source_type"], "HISTORICAL_HYPOTHETICAL")

    def test_12_historical_datasets_remain_unchanged(self):
        before = _hashes(HISTORICAL_DATASETS)
        self.assertTrue(before)
        mgr = self._mgr()
        mgr.start(session_id="hist", mode="offline_synthetic")
        mgr.ingest_synthetic(continuous_bars(3), as_of_utc=replay_as_of(), created_at_utc=created_at())
        mgr.stop()
        after = _hashes(HISTORICAL_DATASETS)
        self.assertEqual(before, after)
        store = ShadowStore(Path(tempfile.mkdtemp()))
        with self.assertRaises(ShadowError):
            store._assert_write_isolated(SRC_DIR / "data" / "xauusd_m5_labeled.csv")

    def test_13_paper_store_remains_unchanged(self):
        before = _hashes(PAPER_ARTIFACTS)
        mgr = self._mgr()
        mgr.start(session_id="paper", mode="offline_synthetic")
        mgr.ingest_synthetic(continuous_bars(2), as_of_utc=replay_as_of(), created_at_utc=created_at())
        for dec in mgr.store.decisions():
            self.assertEqual(str(dec["is_paper_trade"]).lower(), "false")
            self.assertEqual(str(dec["is_paper_execution"]).lower(), "false")
            self.assertNotEqual(dec["source_type"], "AGENT_PAPER")
        after = _hashes(PAPER_ARTIFACTS)
        self.assertEqual(before, after)

    def test_14_session_lock_prevents_concurrent_sessions(self):
        mgr = self._mgr()
        mgr.start(session_id="a", mode="offline_synthetic")
        with self.assertRaises(ShadowError):
            mgr.start(session_id="b", mode="offline_synthetic")
        other = SessionManager(mgr.root)
        with self.assertRaises(ShadowError):
            other.start(session_id="c", mode="offline_synthetic")

    def test_15_restart_does_not_duplicate_records(self):
        tmp = Path(tempfile.mkdtemp())
        a = SessionManager(tmp)
        a.start(session_id="r1", mode="offline_synthetic")
        a.ingest_synthetic(continuous_bars(4), as_of_utc=replay_as_of(), created_at_utc=created_at())
        a.stop()
        b = SessionManager(tmp)
        b.start(session_id="r2", mode="offline_synthetic")
        result = b.ingest_synthetic(continuous_bars(4), as_of_utc=replay_as_of(), created_at_utc=created_at())
        self.assertEqual(result["new_observations"], 0)
        self.assertEqual(len(b.store.observations()), 4)

    def test_16_status_command_is_read_only(self):
        from phase12 import run_phase12
        src = inspect.getsource(run_phase12.main)
        self.assertIn("read_only=True", src)
        tmp = Path(tempfile.mkdtemp())
        writer = SessionManager(tmp)
        writer.start(session_id="st", mode="offline_synthetic")
        writer.ingest_synthetic(continuous_bars(2), as_of_utc=replay_as_of(), created_at_utc=created_at())
        digest_before = hashlib.sha256(writer.store.obs_path.read_bytes()).hexdigest()
        files_before = {p.name: p.stat().st_mtime_ns for p in tmp.iterdir()}
        reader = SessionManager(tmp, read_only=True)
        status = reader.status()
        self.assertEqual(status["observations"], 2)
        with self.assertRaises(ShadowError):
            reader.start(session_id="nope", mode="offline_synthetic")
        with self.assertRaises(ShadowError):
            reader.store.append_session({"session_id": "x"})
        self.assertEqual(hashlib.sha256(writer.store.obs_path.read_bytes()).hexdigest(), digest_before)
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in tmp.iterdir()}, files_before)

    def test_17_summary_command_is_read_only(self):
        from phase12 import run_phase12
        src = inspect.getsource(run_phase12.main)
        self.assertIn("args.summary", src)
        self.assertIn("read_only=True", src)
        tmp = Path(tempfile.mkdtemp())
        writer = SessionManager(tmp)
        writer.start(session_id="sum", mode="offline_synthetic")
        writer.ingest_synthetic(continuous_bars(1), as_of_utc=replay_as_of(), created_at_utc=created_at())
        digest = hashlib.sha256(writer.store.dec_path.read_bytes()).hexdigest()
        reader = SessionManager(tmp, read_only=True)
        summary = reader.status()
        self.assertEqual(summary["decisions"], 1)
        self.assertEqual(hashlib.sha256(writer.store.dec_path.read_bytes()).hexdigest(), digest)

    def test_18_stop_command_preserves_existing_records(self):
        mgr = self._mgr()
        mgr.start(session_id="stop", mode="offline_synthetic")
        mgr.ingest_synthetic(continuous_bars(3), as_of_utc=replay_as_of(), created_at_utc=created_at())
        obs_before = list(mgr.store.observations())
        dec_before = list(mgr.store.decisions())
        mgr.stop()
        self.assertFalse(mgr.status()["running"])
        reopened = SessionManager(mgr.root, read_only=True)
        self.assertEqual(len(reopened.store.observations()), len(obs_before))
        self.assertEqual(len(reopened.store.decisions()), len(dec_before))
        self.assertEqual(
            [r["observation_id"] for r in reopened.store.observations()],
            [r["observation_id"] for r in obs_before],
        )

    def test_19_no_broker_order_function_invocation(self):
        self.assertEqual(broker_order_calls(), 0)
        tree = audit_phase12_tree(PHASE12_ROOT)
        self.assertEqual(tree["prohibited_any"], [])
        # Mutation / check APIs remain prohibited. Phase64.8 approved positions_get/orders_get
        # as read-only evidence APIs — they must still not appear in the Phase12 metadata adapter.
        for name in ("order_send", "order_check"):
            self.assertIn(name, PROHIBITED_MT5_API)
            self.assertNotIn(name, audit_source(ADAPTER)["permitted_used"])
        for name in ("positions_get", "orders_get", "history_deals_get", "history_orders_get"):
            self.assertIn(name, PERMITTED_MT5_API)
            self.assertNotIn(name, audit_source(ADAPTER)["permitted_used"])

    def test_20_no_actual_mt5_connection_during_tests(self):
        self.assertNotIn("MetaTrader5", sys.modules)
        self.assertEqual(mt5_connections(), 0)
        snap = snapshot_protected()
        self.assertTrue(all(v["unchanged"] for v in snap.values()))
        from phase12.mt5_readonly import connect_readonly
        self.assertTrue(callable(connect_readonly))
        self.assertNotIn("MetaTrader5", sys.modules)


if __name__ == "__main__":
    unittest.main()
