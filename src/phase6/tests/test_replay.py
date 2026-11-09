import unittest

from phase6.decision_engine import DecisionEngine
from phase6.information_boundary import InformationBoundaryError
from phase6.predictor import NullPredictor
from phase6.replay import HistoricalBar, HistoricalReplay, ObservationBuilder
from phase6.risk_gate import RiskGate


def bars():
    return [
        HistoricalBar("2026-06-01 10:00:00", 1, 2, 0.5, 1.2, 10, 0.15, (("atr14", 1.0),)),
        HistoricalBar("2026-06-01 10:05:00", 1.2, 2.1, 1.0, 1.4, 11, 0.15, (("atr14", 1.1),)),
        HistoricalBar("2026-06-01 10:10:00", 1.4, 2.2, 1.1, 1.5, 12, 0.15, (("atr14", 1.2),)),
    ]


class ReplayTests(unittest.TestCase):
    def test_processes_timestamps_chronologically(self):
        replay = HistoricalReplay(bars(), NullPredictor(), DecisionEngine(), RiskGate())
        replay.run()
        self.assertEqual(
            replay.processed,
            ["2026-06-01 10:00:00", "2026-06-01 10:05:00", "2026-06-01 10:10:00"],
        )
        self.assertEqual([r["timestamp"] for r in replay.journal.decision_time_rows()], replay.processed)

    def test_rejects_out_of_order_replay(self):
        replay = HistoricalReplay(bars(), NullPredictor(), DecisionEngine(), RiskGate())
        with self.assertRaises(InformationBoundaryError):
            replay.run(["2026-06-01 10:10:00", "2026-06-01 10:00:00"])

    def test_builder_does_not_see_future_bars(self):
        builder = ObservationBuilder(bars())
        prefix = builder.prefix("2026-06-01 10:05:00")
        self.assertEqual([b.timestamp for b in prefix], ["2026-06-01 10:00:00", "2026-06-01 10:05:00"])
        self.assertTrue(all(b.timestamp <= "2026-06-01 10:05:00" for b in prefix))

    def test_null_replay_final_wait(self):
        replay = HistoricalReplay(bars(), NullPredictor(), DecisionEngine(), RiskGate())
        journal = replay.run()
        self.assertTrue(all(r["final_decision"] == "WAIT" for r in journal.decision_time_rows()))


if __name__ == "__main__":
    unittest.main()
