import unittest

from phase6.information_boundary import InformationBoundaryError
from phase6.schemas import Observation
from phase7.observation_builder import build_observation
from phase7.tests.synth import pair


class ObservationBoundaryTests(unittest.TestCase):
    def test_realized_outcome_cannot_enter_observation(self):
        payload = pair("2026-06-19 03:05:00")
        payload["actual_net_r"] = 1.5
        with self.assertRaises(InformationBoundaryError):
            build_observation(payload)

    def test_builder_output_has_no_outcome_fields(self):
        obs = build_observation(pair("2026-06-19 03:05:00"))
        mapping = obs.to_mapping()
        self.assertNotIn("actual_net_r", mapping)
        self.assertNotIn("exit_reason", mapping)
        self.assertIsInstance(obs, Observation)


if __name__ == "__main__":
    unittest.main()
