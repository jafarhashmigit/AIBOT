import unittest

from phase6.journal import OUTCOME_FIELDS
from phase7.phase2_predictor_adapter import Phase2PredictorAdapter
from phase7.run_oos_agent import _assert_chronological, generate_agent_decisions, join_evaluation
from phase7.tests.synth import ev, pair


class JournalEvalChronoTests(unittest.TestCase):
    def test_journal_has_no_realized_outcome(self):
        pairs = [pair("2026-06-19 03:05:00"), pair("2026-06-19 03:10:00")]
        rows, raw, final, chrono, _ = generate_agent_decisions(pairs, Phase2PredictorAdapter(pairs))
        for row in rows:
            for name in OUTCOME_FIELDS:
                self.assertNotIn(name, row)
            self.assertNotIn("realized_R", row)
            self.assertNotIn("actual_net_r", row)
            self.assertEqual(row["final_decision"], "WAIT")

    def test_outcome_joined_only_after_decisions(self):
        pairs = [pair("2026-06-19 03:05:00")]
        rows, *_ = generate_agent_decisions(pairs, Phase2PredictorAdapter(pairs))
        joined = join_evaluation(rows, [ev("2026-06-19 03:05:00")])
        self.assertEqual(joined[0]["evaluation_metadata"], "joined_after_decisions")
        self.assertIn("realized_R", joined[0])
        self.assertNotIn("realized_R", rows[0])

    def test_chronology_rejects_backward(self):
        with self.assertRaises(RuntimeError):
            _assert_chronological(["2026-06-19 03:10:00", "2026-06-19 03:05:00"])

    def test_reproducible_decisions(self):
        pairs = [pair("2026-06-19 03:05:00", buy_r=0.4), pair("2026-06-19 03:10:00", buy_r=-0.2)]
        a, *_ = generate_agent_decisions(pairs, Phase2PredictorAdapter(pairs))
        b, *_ = generate_agent_decisions(pairs, Phase2PredictorAdapter(pairs))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
