import unittest

from phase6.information_boundary import InformationBoundaryError
from phase8.experience_schema import assert_no_outcome_keys, outcome_end_for
from phase8.tests.factories import decision


class SchemaTests(unittest.TestCase):
    def test_decision_time_rejects_outcome_keys(self):
        with self.assertRaises(InformationBoundaryError):
            assert_no_outcome_keys({"timestamp": "2026-06-19 03:05:00", "realized_R": 1.0})

    def test_horizon_is_sixty_minutes(self):
        self.assertEqual(outcome_end_for("2026-06-19 10:00:00"), "2026-06-19 11:00:00")

    def test_decision_fields_roundtrip(self):
        d = decision("2026-06-19 10:00:00")
        self.assertNotIn("hypothetical_buy_net_r", d.to_mapping())
        self.assertEqual(d.action, "WAIT")


if __name__ == "__main__":
    unittest.main()
