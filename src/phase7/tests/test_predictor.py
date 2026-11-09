import unittest

from phase7.phase2_predictor_adapter import Phase2PredictorAdapter
from phase7.observation_builder import build_observation
from phase7.tests.synth import pair


class PredictorTests(unittest.TestCase):
    def test_adapter_cannot_fit(self):
        adapter = Phase2PredictorAdapter([pair("2026-06-19 03:05:00")])
        with self.assertRaises(RuntimeError):
            adapter.fit([], [], training_end="2026-05-01 00:00:00")

    def test_predict_is_lookup(self):
        p = pair("2026-06-19 03:05:00", buy_r=0.2, sell_r=-0.3)
        adapter = Phase2PredictorAdapter([p])
        obs = build_observation(p)
        pred = adapter.predict(obs)
        self.assertAlmostEqual(pred.expected_buy_r, 0.2)
        self.assertAlmostEqual(pred.expected_sell_r, -0.3)
        self.assertEqual(pred.model_id, "phase2_rf_oos")


if __name__ == "__main__":
    unittest.main()
