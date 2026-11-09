import unittest

from phase6.information_boundary import InformationBoundaryError
from phase6.journal import DecisionJournal
from phase6.outcome import Outcome, attach_outcome
from phase6.tests.factories import observation, record_wait_decision


class OutcomeTests(unittest.TestCase):
    def test_cannot_attach_before_horizon(self):
        obs = observation("2026-06-01 10:00:00")
        out = Outcome(
            entry_timestamp="2026-06-01 10:05:00",
            exit_timestamp="2026-06-01 10:30:00",
            exit_reason="TIME",
            gross_return_usd=0.0,
            cost_usd=0.25,
            net_return_r=-0.1,
            duration_bars=6,
        )
        with self.assertRaises(InformationBoundaryError):
            attach_outcome(obs, out, evaluation_timestamp="2026-06-01 10:30:00")

    def test_can_attach_after_horizon(self):
        obs = observation("2026-06-01 10:00:00")
        out = Outcome(
            entry_timestamp="2026-06-01 10:05:00",
            exit_timestamp="2026-06-01 11:00:00",
            exit_reason="SL",
            gross_return_usd=-2.0,
            cost_usd=0.25,
            net_return_r=-1.0,
            duration_bars=12,
        )
        payload = attach_outcome(obs, out, evaluation_timestamp="2026-06-01 11:00:00")
        self.assertEqual(payload["realized_R"], -1.0)
        self.assertNotIn("realized_R", obs.to_mapping())

    def test_journal_enrichment_is_separate_row(self):
        journal, row = record_wait_decision()
        out = Outcome(
            entry_timestamp="2026-06-01 10:05:00",
            exit_timestamp="2026-06-01 11:00:00",
            exit_reason="TP",
            gross_return_usd=3.0,
            cost_usd=0.25,
            net_return_r=1.5,
            duration_bars=12,
        )
        journal.attach_outcome(row["decision_id"], out, evaluation_timestamp="2026-06-01 11:05:00")
        decision_rows = journal.decision_time_rows()
        self.assertEqual(len(decision_rows), 1)
        self.assertNotIn("realized_R", decision_rows[0])
        self.assertEqual(journal.rows[-1]["kind"], "outcome_enrichment")


if __name__ == "__main__":
    unittest.main()
