import unittest

from phase6.decision_engine import DecisionEngine
from phase6.tests.factories import costs, observation, prediction, uncertainty


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()
        self.obs = observation()
        self.costs = costs()
        self.unc = uncertainty()

    def test_outputs_are_buy_sell_or_wait(self):
        cases = [
            (0.0, 0.0),
            (1.0, -1.0),
            (-1.0, 1.0),
            (0.5, 0.5),
        ]
        for buy_r, sell_r in cases:
            result = self.engine.decide(self.obs, prediction(buy_r=buy_r, sell_r=sell_r), self.unc, self.costs)
            self.assertIn(result.raw_decision, {"BUY", "SELL", "WAIT"})

    def test_positive_buy_ev_can_be_buy(self):
        result = self.engine.decide(self.obs, prediction(buy_r=1.0, sell_r=-1.0), self.unc, self.costs)
        self.assertEqual(result.raw_decision, "BUY")

    def test_positive_sell_ev_can_be_sell(self):
        result = self.engine.decide(self.obs, prediction(buy_r=-1.0, sell_r=1.0), self.unc, self.costs)
        self.assertEqual(result.raw_decision, "SELL")

    def test_zero_ev_is_wait(self):
        result = self.engine.decide(self.obs, prediction(buy_r=0.0, sell_r=0.0), self.unc, self.costs)
        self.assertEqual(result.raw_decision, "WAIT")

    def test_both_positive_is_conflict_wait(self):
        result = self.engine.decide(self.obs, prediction(buy_r=1.0, sell_r=1.0), self.unc, self.costs)
        self.assertEqual(result.raw_decision, "WAIT")
        self.assertEqual(result.reason, "CONFLICT")

    def test_does_not_read_outcome_attributes(self):
        self.assertFalse(hasattr(self.obs, "net_return_r"))
        self.assertFalse(hasattr(self.obs, "exit_reason"))


if __name__ == "__main__":
    unittest.main()
