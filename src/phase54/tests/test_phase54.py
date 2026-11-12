"""Phase54 automated tests — synthetic fixtures only (not historical evidence)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase54.archive_loader import ForbiddenArchiveDateError, assert_day_allowed
from phase54.decision import NullPolicy, decide
from phase54.experience import historical_store, record_agent_shadow, shadow_store, stores_are_isolated
from phase54.lifecycle import LifecycleEngine
from phase54.observer import build_observation, validate_bar
from phase54.paper_exec import PaperExecutionError, open_paper_position, force_horizon_exit_from_bars
from phase54.reporting import build_operational_report
from phase54.risk import RiskManager
from phase54.state import AgentState
from phase54.tests.fixtures import synthetic_day


class TestObserver(unittest.TestCase):
    def test_valid_and_invalid_bars(self):
        self.assertEqual(validate_bar({"timestamp_utc": "t", "open": 1, "high": 2, "low": 0.5, "close": 1.5}), [])
        self.assertTrue(validate_bar({"timestamp_utc": "t", "open": 1, "high": 0.5, "low": 2, "close": 1}))

    def test_observation_accept_reject(self):
        day, m5, h1, by = synthetic_day()
        ok = build_observation(m5=m5, idx=48, h1=h1, ticks_by_bar=by, day=day)
        self.assertTrue(ok["accepted"])
        bad = build_observation(m5=m5, idx=10, h1=h1, ticks_by_bar=by, day=day)
        self.assertFalse(bad["accepted"])


class TestDecision(unittest.TestCase):
    def test_default_wait(self):
        day, m5, h1, by = synthetic_day()
        obs = build_observation(m5=m5, idx=48, h1=h1, ticks_by_bar=by, day=day)
        d = decide(obs, obs["features"], None, {}, policy=NullPolicy())
        self.assertEqual(d["action"], "WAIT")
        self.assertIsNone(d["expected_net_r"])
        self.assertIsNone(d["prob_positive"])
        self.assertFalse(d["calibrated_probabilities"])
        self.assertIn("NO_MODEL", d["reason_codes"])


class TestRisk(unittest.TestCase):
    def test_limits_and_circuit(self):
        rm = RiskManager({"max_simultaneous_positions": 1, "circuit_breaker_errors": 2})
        dec = {"proposed_action": "BUY", "action": "BUY"}
        ms = {"day": "2099-01-06", "spread": 0.1, "atr": 1.0, "symbol": "XAUUSD", "market_state_id": "a"}
        g = rm.evaluate(dec, ms)
        # Null policy path not used — risk allows if limits ok
        self.assertTrue(g["allowed"])
        rm.register_open("p1", {"market_state_id": "a", "side": "BUY", "symbol": "XAUUSD"})
        g2 = rm.evaluate(dec, {**ms, "market_state_id": "b"})
        self.assertEqual(g2["final_action"], "WAIT")
        self.assertIn("max_simultaneous_positions", g2["reasons"])
        rm.note_error()
        rm.note_error()
        self.assertTrue(rm.circuit_open)
        g3 = rm.evaluate(dec, ms)
        self.assertEqual(g3["final_action"], "WAIT")
        self.assertIn("circuit_breaker", g3["reasons"])

    def test_invalid_stop(self):
        rm = RiskManager()
        s = rm.position_size(atr=None)
        self.assertFalse(s["ok"])


class TestPaperExec(unittest.TestCase):
    def test_buy_sell_bid_ask(self):
        day, m5, h1, by = synthetic_day()
        obs = build_observation(m5=m5, idx=48, h1=h1, ticks_by_bar=by, day=day)
        for side in ("BUY", "SELL"):
            dec = {
                "decision_id": "d1",
                "action": side,
                "observation_id": obs["observation_id"],
            }
            entry_idx = 49
            pos = open_paper_position(
                decision=dec,
                market_state=obs,
                entry_bar_ts=str(m5[entry_idx]["timestamp_utc"]),
                ticks_by_bar=by,
                sizing={"units": 1.0, "stop_distance": 1.0},
                m5=m5,
                entry_idx=entry_idx,
            )
            if side == "BUY":
                self.assertEqual(pos["entry_fill"], pos["entry_ask"])
            else:
                self.assertEqual(pos["entry_fill"], pos["entry_bid"])
            closed = force_horizon_exit_from_bars(pos, m5=m5, ticks_by_bar=by, horizon_bars=12)
            self.assertEqual(closed["status"], "CLOSED")
            if side == "BUY":
                self.assertEqual(closed["exit_fill"], closed["exit_bid"])
            else:
                self.assertEqual(closed["exit_fill"], closed["exit_ask"])

    def test_wait_cannot_open(self):
        with self.assertRaises(PaperExecutionError):
            open_paper_position(
                decision={"decision_id": "x", "action": "WAIT"},
                market_state={"atr": 1},
                entry_bar_ts="t",
                ticks_by_bar={},
                sizing={"stop_distance": 1},
                m5=[],
                entry_idx=0,
            )


class TestLifecycle(unittest.TestCase):
    def test_pipeline_wait_and_idempotency_and_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            sp = Path(td) / "state.json"
            # isolate experience roots via monkeypatch paths — use clear on phase54 stores carefully
            hist = historical_store()
            shadow = shadow_store()
            hist.clear()
            shadow.clear()
            engine = LifecycleEngine(state=AgentState(path=sp), risk=RiskManager())
            day, m5, h1, by = synthetic_day()
            r1 = engine.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertFalse(r1.get("rejected"))
            self.assertEqual(r1["decision"]["action"], "WAIT")
            self.assertGreaterEqual(engine.shadow.n, 1)
            self.assertGreaterEqual(engine.hist.n, 2)  # BUY+SELL counterfactuals
            r2 = engine.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertTrue(r2.get("skipped"))
            # restart
            engine2 = LifecycleEngine(state=AgentState(path=sp), risk=RiskManager())
            r3 = engine2.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertTrue(r3.get("skipped"))
            self.assertTrue(stores_are_isolated(engine.hist, engine.shadow))


class TestExperienceIsolation(unittest.TestCase):
    def test_no_cross_append(self):
        hist = historical_store()
        shadow = shadow_store()
        self.assertTrue(stores_are_isolated(hist, shadow))
        with self.assertRaises(ValueError):
            hist.append({"source": "AGENT_SHADOW"})


class TestForbiddenDates(unittest.TestCase):
    def test_phase44_blocked(self):
        with self.assertRaises(ForbiddenArchiveDateError):
            assert_day_allowed("2025-10-27")


class TestReporting(unittest.TestCase):
    def test_report_consistency(self):
        with tempfile.TemporaryDirectory() as td:
            st = AgentState(path=Path(td) / "s.json")
            st.bump("observations", 2)
            st.bump("wait", 2)
            st.data["last_success_iso"] = "2026-01-01T00:00:00Z"
            rep = build_operational_report(
                state=st,
                risk_snap=RiskManager().snapshot(),
                hist_n=1,
                shadow_n=2,
            )
            self.assertFalse(rep["validated_profitable_policy"])
            self.assertEqual(rep["action_counts"]["WAIT"], 2)
            self.assertIn("utc", rep["generated"])
            self.assertIn("pkt", rep["generated"])


class TestForcedBuyRiskBlock(unittest.TestCase):
    """Directional proposal still blocked by circuit / risk — policy remains separate."""

    def test_risk_forces_wait(self):
        class BuyPolicy:
            version = "test_buy"

            def propose(self, market_state, features, model_output, risk_state):
                return {
                    "action": "BUY",
                    "expected_net_r": None,
                    "prob_positive": None,
                    "calibrated": False,
                    "confidence": None,
                    "uncertainty": 1.0,
                    "reason_codes": ["TEST_ONLY"],
                }

        rm = RiskManager()
        rm.circuit_open = True
        rm.safety_state = "CIRCUIT_BREAKER_WAIT"
        day, m5, h1, by = synthetic_day()
        with tempfile.TemporaryDirectory() as td:
            eng = LifecycleEngine(
                state=AgentState(path=Path(td) / "s.json"),
                risk=rm,
                policy=BuyPolicy(),
                record_counterfactuals=False,
            )
            hist = historical_store()
            shadow = shadow_store()
            # don't clear shared stores mid-other-tests heavily — just process
            r = eng.process_bar(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(r["decision"]["action"], "WAIT")
            self.assertIn("circuit_breaker", r["decision"]["risk_gate"]["reasons"])


if __name__ == "__main__":
    unittest.main()
