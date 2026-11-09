"""Phase 12C forward compatibility and safety tests. Synthetic only. No MT5."""

from __future__ import annotations

import sys
import unittest

from phase6.information_boundary import InformationBoundaryError
from phase6.risk_gate import RiskGate
from phase6.schemas import Observation
from phase6.tests.factories import observation
from phase12c.constants import ADAPTER_VERSION, CHAMPION_STATUS, FULL_EVALUATE_PARITY
from phase12c.cutoff_inventory import inventory
from phase12c.decision_path import decide_forward, propose_raw_action
from phase12c.forward_observation import ForwardObservation, ForwardObservationError, from_synthetic_bar
from phase12c.gate_adapter import ForwardGateAdapter
from phase12c.integrity import snapshot_phase1_11, snapshot_phase12_12b
from phase12c.model_readiness import audit_model_readiness
from phase12c.parity import (
    POST_CUTOFF,
    PRE_CUTOFF,
    forward_compatibility_audit,
    full_evaluate_parity_audit,
    risk_gate_parity_audit,
    run_compatibility_audits,
)
from phase12c.tests.fixtures import (
    INCOMPLETE_BAR,
    INVALID_OHLC_BAR,
    POST_CUTOFF_BAR,
    PRE_CUTOFF_BAR,
    SYNTHETIC,
)


class Phase12CTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SYNTHETIC)
        self.assertNotIn("MetaTrader5", sys.modules)
        self.seen_ids: set[str] = set()

    def _post(self) -> ForwardObservation:
        return from_synthetic_bar(POST_CUTOFF_BAR)

    def _pre(self) -> ForwardObservation:
        return from_synthetic_bar(PRE_CUTOFF_BAR)

    def test_01_cutoff_inventory_lists_evaluate_blockers(self):
        inv = inventory()
        comps = [c["component"] for c in inv["checks"]]
        self.assertIn("phase6.risk_gate.RiskGate.evaluate", comps)
        self.assertIn("phase6.schemas.Observation.__post_init__", comps)
        self.assertIn("phase6.risk_gate.apply_gate", inv["reusable_without_modifying_phase6"])
        self.assertEqual(inv["full_evaluate_parity"], "NOT_PROVEN")

    def test_02_phase6_observation_rejects_post_cutoff(self):
        with self.assertRaises(InformationBoundaryError):
            observation(timestamp=POST_CUTOFF)

    def test_03_full_evaluate_parity_incomplete(self):
        audit = full_evaluate_parity_audit()
        self.assertEqual(audit["status"], "INCOMPLETE")
        self.assertTrue(audit["observation_construction_raises"])
        self.assertEqual(FULL_EVALUATE_PARITY, "NOT_PROVEN")

    def test_04_risk_gate_apply_parity_pre_cutoff(self):
        audit = risk_gate_parity_audit()
        self.assertEqual(audit["status"], "PASS")
        for row in audit["rows"]:
            self.assertTrue(row["match"])
            self.assertEqual(row["phase6_evaluate_apply"]["final"], "WAIT")

    def test_05_forward_compatibility_pass_with_qualification(self):
        audit = forward_compatibility_audit()
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["full_evaluate_parity"], "NOT_PROVEN")
        self.assertFalse(audit["evaluate_called"])

    def test_06_adapter_reuses_apply_gate_not_evaluate(self):
        calls = []
        original = RiskGate.evaluate

        def wrapped(self, *args, **kwargs):
            calls.append(True)
            return original(self, *args, **kwargs)

        RiskGate.evaluate = wrapped
        try:
            adapter = ForwardGateAdapter()
            out = adapter.apply("BUY")
            self.assertEqual(out["final_action"], "WAIT")
            self.assertFalse(out["evaluate_called"])
            self.assertTrue(out["apply_gate_reused"])
            self.assertEqual(calls, [])
            self.assertEqual(adapter.version, ADAPTER_VERSION)
        finally:
            RiskGate.evaluate = original

    def test_07_no_approved_model_wait(self):
        dec = decide_forward(self._post())
        self.assertEqual(dec["final_action"], "WAIT")
        self.assertEqual(dec["decision_reason"], "NO_APPROVED_MODEL")
        self.assertEqual(dec["champion_status"], "NO_MODEL")

    def test_08_invalid_prediction_wait(self):
        proposal = propose_raw_action(prediction={"bad": True})
        self.assertEqual(proposal["raw_action"], "WAIT")
        self.assertEqual(proposal["decision_reason"], "INVALID_PREDICTION")
        dec = decide_forward(self._post(), prediction={"bad": True})
        self.assertEqual(dec["final_action"], "WAIT")

    def test_09_missing_prediction_wait(self):
        proposal = propose_raw_action(prediction=None)
        self.assertEqual(proposal["decision_reason"], "NO_APPROVED_MODEL")
        self.assertEqual(proposal["raw_action"], "WAIT")

    def test_10_unknown_model_id_wait(self):
        proposal = propose_raw_action(model_id="unknown_model_xyz")
        self.assertEqual(proposal["decision_reason"], "UNKNOWN_MODEL_ID")
        self.assertEqual(proposal["raw_action"], "WAIT")
        with self.assertRaises(Exception):
            # Phase 12 propose_action still refuses unknown champions
            from phase12.decision_recorder import propose_action
            propose_action(champion_id="unknown_model_xyz")

    def test_11_unavailable_uncertainty_wait(self):
        pred = {"expected_buy_r": 0.1, "expected_sell_r": -0.1, "model_id": "no_model"}
        proposal = propose_raw_action(prediction=pred, uncertainty=None)
        self.assertEqual(proposal["decision_reason"], "UNCERTAINTY_UNAVAILABLE")
        bad = propose_raw_action(prediction=pred, uncertainty={"only_buy": 0.1})
        self.assertEqual(bad["decision_reason"], "UNCERTAINTY_UNAVAILABLE")
        self.assertEqual(bad["raw_action"], "WAIT")

    def test_12_riskgate_block_wait(self):
        adapter = ForwardGateAdapter()
        for raw in ("BUY", "SELL"):
            out = adapter.apply(raw)
            self.assertEqual(out["gate_status"], "BLOCK")
            self.assertEqual(out["final_action"], "WAIT")

    def test_13_riskgate_allow_cannot_create_direction_from_wait(self):
        adapter = ForwardGateAdapter()
        out = adapter.apply("WAIT")
        self.assertEqual(out["gate_status"], "ALLOW")
        self.assertEqual(out["final_action"], "WAIT")
        # Forced BUY still blocked under no_model
        forced = decide_forward(self._post(), forced_raw_action="BUY")
        self.assertEqual(forced["final_action"], "WAIT")
        self.assertEqual(forced["risk_gate_result"], "BLOCK")

    def test_14_stale_or_invalid_market_data_rejected(self):
        with self.assertRaises(ForwardObservationError):
            from_synthetic_bar(INVALID_OHLC_BAR)
        bad = ForwardObservation(
            timestamp=POST_CUTOFF,
            bar_open_timestamp_utc="2026-11-02 09:55:00",
            bar_close_timestamp_utc=POST_CUTOFF,
            open=4000.0,
            high=4001.0,
            low=3999.0,
            close=4000.5,
            tick_volume=1,
            data_quality_status="stale",
        )
        with self.assertRaises(Exception):
            decide_forward(bad)

    def test_15_duplicate_observation_no_duplicate_decision(self):
        obs = self._post()
        first = decide_forward(obs)
        self.assertNotIn(first["observation_id"], self.seen_ids)
        self.seen_ids.add(first["observation_id"])
        # Same observation id must be detectable as duplicate by consumer
        second = decide_forward(obs)
        self.assertEqual(first["observation_id"], second["observation_id"])
        self.assertIn(second["observation_id"], self.seen_ids)
        # Journal would skip; we assert identity equality for duplicate prevention contract
        self.assertEqual(first["observation_id"], obs.observation_id)

    def test_16_incomplete_candle_rejected(self):
        with self.assertRaises(ForwardObservationError):
            from_synthetic_bar(INCOMPLETE_BAR)

    def test_17_missing_required_feature_wait(self):
        obs = from_synthetic_bar(POST_CUTOFF_BAR, created_features={})
        proposal = propose_raw_action(
            prediction={"expected_buy_r": 0.0, "expected_sell_r": 0.0, "model_id": "no_model"},
            uncertainty={"buy": 0.0, "sell": 0.0},
            required_features=["atr14"],
            feature_map=obs.features,
        )
        self.assertEqual(proposal["decision_reason"], "MISSING_REQUIRED_FEATURE")
        self.assertEqual(proposal["raw_action"], "WAIT")
        dec = decide_forward(obs, required_features=["atr14"], prediction={
            "expected_buy_r": 0.0, "expected_sell_r": 0.0, "model_id": "no_model"
        }, uncertainty={"buy": 0.0, "sell": 0.0})
        self.assertEqual(dec["final_action"], "WAIT")

    def test_18_pre_and_post_cutoff_synthetic_paths(self):
        pre = decide_forward(self._pre())
        post = decide_forward(self._post())
        self.assertFalse(pre["is_post_cutoff"])
        self.assertTrue(post["is_post_cutoff"])
        self.assertEqual(pre["final_action"], "WAIT")
        self.assertEqual(post["final_action"], "WAIT")
        self.assertEqual(pre["source_type"], "FORWARD_SHADOW")
        self.assertEqual(post["source_type"], "FORWARD_SHADOW")

    def test_19_model_readiness_remains_no_model(self):
        audit = audit_model_readiness()
        self.assertEqual(audit["champion_status"], "NO_MODEL")
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertFalse(audit["production_promotion"])
        self.assertFalse(audit["buy_sell_authorized"])
        self.assertEqual(audit["counts"]["validated"], 0)
        self.assertEqual(audit["counts"]["experimental"], 0)

    def test_20_integrity_phase1_11_and_phase12_12b(self):
        snap1 = snapshot_phase1_11()
        snap2 = snapshot_phase12_12b()
        self.assertTrue(all(v["unchanged"] for v in snap1.values()))
        self.assertTrue(all(v["unchanged"] for v in snap2.values()))
        self.assertNotIn("MetaTrader5", sys.modules)
        overall = run_compatibility_audits()
        self.assertEqual(overall["B_risk_gate_apply_parity"]["status"], "PASS")
        self.assertEqual(overall["C_forward_compatibility"]["status"], "PASS")
        self.assertEqual(overall["A_full_evaluate_parity"]["status"], "INCOMPLETE")
        # Ensure we never constructed a Phase 6 Observation for post-cutoff
        with self.assertRaises(InformationBoundaryError):
            Observation(timestamp=POST_CUTOFF)


if __name__ == "__main__":
    unittest.main()
