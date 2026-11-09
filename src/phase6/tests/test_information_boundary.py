import unittest

from phase6.information_boundary import InformationBoundaryError, assert_decision_time_payload
from phase6.outcome import observation_rejects_outcome_fields
from phase6.schemas import Observation
from phase6.tests.factories import observation


class InformationBoundaryTests(unittest.TestCase):
    def test_future_outcome_cannot_enter_observation_from_mapping(self):
        payload = observation().to_mapping()
        payload["realized_R"] = 1.5
        with self.assertRaises(InformationBoundaryError):
            Observation.from_mapping(payload)

    def test_net_r_feature_name_rejected(self):
        with self.assertRaises(InformationBoundaryError):
            observation(features={"net_r": 0.1})

    def test_exit_reason_payload_rejected(self):
        with self.assertRaises(InformationBoundaryError):
            assert_decision_time_payload({"timestamp": "2026-06-01 10:00:00", "exit_reason": "TP"})

    def test_outcome_fields_are_not_observation_fields(self):
        self.assertTrue(observation_rejects_outcome_fields())

    def test_post_cutoff_observation_rejected(self):
        with self.assertRaises(InformationBoundaryError):
            observation(timestamp="2026-09-29 18:55:00")

    def test_history_end_must_equal_timestamp(self):
        with self.assertRaises(InformationBoundaryError):
            Observation(
                timestamp="2026-06-01 10:00:00",
                available_history_end="2026-06-01 10:05:00",
            )


if __name__ == "__main__":
    unittest.main()
