import unittest

from phase6.decision_engine import DecisionEngine
from phase6.risk_gate import RiskGate
from phase6.schemas import CostEstimate, Uncertainty
from phase7.constants import ESTIMATED_COST_USD
from phase7.observation_builder import build_observation
from phase7.phase2_predictor_adapter import Phase2PredictorAdapter
from phase7.tests.synth import pair


class DecisionAndGateTests(unittest.TestCase):
    def test_decision_goes_through_phase6_engine(self):
        p = pair("2026-06-19 03:05:00", buy_r=1.0, sell_r=-1.0)
        adapter = Phase2PredictorAdapter([p])
        obs = build_observation(p)
        pred = adapter.predict(obs)
        engine = DecisionEngine()
        result = engine.decide(obs, pred, Uncertainty("none", 0.0, 0.0),
                               CostEstimate(ESTIMATED_COST_USD, "test"))
        self.assertEqual(result.raw_decision, "BUY")
        self.assertEqual(result.decision_engine_version, engine.version)

    def test_risk_gate_does_not_change_prediction(self):
        p = pair("2026-06-19 03:05:00", buy_r=1.0, sell_r=-1.0)
        adapter = Phase2PredictorAdapter([p])
        obs = build_observation(p)
        pred = adapter.predict(obs)
        before = (pred.expected_buy_r, pred.expected_sell_r, pred.buy.tp)
        gate = RiskGate()
        gate.evaluate(obs, pred, {"raw_decision": "BUY"})
        after = adapter.predict(obs)
        self.assertEqual(before, (after.expected_buy_r, after.expected_sell_r, after.buy.tp))
        self.assertEqual(pred.expected_buy_r, after.expected_buy_r)


if __name__ == "__main__":
    unittest.main()
