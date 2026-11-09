import unittest

from phase6.decision_engine import DecisionEngine
from phase6.risk_gate import RiskGate, apply_gate
from phase6.tests.factories import costs, observation, prediction, uncertainty


class RiskGateTests(unittest.TestCase):
    def test_blocked_buy_cannot_be_final_buy(self):
        engine = DecisionEngine()
        obs = observation()
        pred = prediction(buy_r=1.0, sell_r=-1.0)
        raw = engine.decide(obs, pred, uncertainty(), costs())
        self.assertEqual(raw.raw_decision, "BUY")
        gate = RiskGate(wait_only=True, champion_id="no_model")
        result = gate.evaluate(obs, pred, {"raw_decision": raw.raw_decision})
        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(apply_gate(raw.raw_decision, result), "WAIT")

    def test_blocked_sell_cannot_be_final_sell(self):
        raw = "SELL"
        gate = RiskGate(wait_only=True)
        result = gate.evaluate(observation(), prediction(), {"raw_decision": raw})
        self.assertEqual(apply_gate(raw, result), "WAIT")

    def test_gate_does_not_create_buy_from_wait(self):
        gate = RiskGate(wait_only=False, champion_id="scripted_test")
        result = gate.evaluate(observation(), prediction(), {"raw_decision": "WAIT"})
        self.assertEqual(apply_gate("WAIT", result), "WAIT")

    def test_allow_path_keeps_raw_side(self):
        gate = RiskGate(wait_only=False, champion_id="scripted_test")
        result = gate.evaluate(observation(), prediction(), {"raw_decision": "BUY"})
        self.assertEqual(result.status, "ALLOW")
        self.assertEqual(apply_gate("BUY", result), "BUY")


if __name__ == "__main__":
    unittest.main()
