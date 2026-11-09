import unittest

from phase6.journal import OUTCOME_FIELDS
from phase6.tests.factories import record_wait_decision


class JournalTests(unittest.TestCase):
    def _record(self):
        return record_wait_decision()

    def test_decision_time_record_has_no_realized_outcome(self):
        _journal, row = self._record()
        for field in OUTCOME_FIELDS:
            self.assertNotIn(field, row)
        self.assertIn("final_decision", row)
        self.assertIn("raw_decision", row)
        self.assertIn("risk_gate_decision", row)

    def test_required_fields_present(self):
        _journal, row = self._record()
        required = [
            "decision_id", "timestamp", "instrument", "timeframe",
            "observation_version", "feature_version", "model_version",
            "prediction", "uncertainty", "estimated_cost",
            "raw_decision", "risk_gate_decision", "final_decision", "decision_reason",
        ]
        for name in required:
            self.assertIn(name, row)


if __name__ == "__main__":
    unittest.main()
