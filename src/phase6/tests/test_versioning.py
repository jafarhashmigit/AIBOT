import unittest

from phase6.decision_engine import DecisionEngine
from phase6.journal import DecisionJournal
from phase6.risk_gate import RiskGate
from phase6.tests.factories import costs, observation, prediction, uncertainty
from phase6.versioning import versions_for


class VersioningTests(unittest.TestCase):
    def test_signal_record_contains_component_versions(self):
        obs = observation()
        pred = prediction(model_id="scripted_test")
        decision = DecisionEngine().decide(obs, pred, uncertainty(), costs())
        gate = RiskGate().evaluate(obs, pred, {"raw_decision": decision.raw_decision})
        versions = versions_for(
            obs,
            model_id=pred.model_id,
            decision_engine_version=DecisionEngine().version,
            risk_gate_version=RiskGate().version,
        )
        row = DecisionJournal().record_decision(
            obs, pred, uncertainty(), costs(), decision, gate, versions
        )
        self.assertTrue(row["signal_id"])
        self.assertEqual(row["model_version"], "scripted_test")
        self.assertTrue(row["feature_version"])
        self.assertTrue(row["decision_engine_version"])
        self.assertTrue(row["risk_gate_version"])
        self.assertTrue(row["cost_assumption_version"])


if __name__ == "__main__":
    unittest.main()
