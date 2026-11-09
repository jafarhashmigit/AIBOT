import unittest

from phase6.decision_engine import DecisionEngine
from phase6.predictor import NullPredictor
from phase6.replay import HistoricalBar, HistoricalReplay
from phase6.risk_gate import RiskGate


def bars():
    return [
        HistoricalBar("2026-06-01 10:00:00", 1, 2, 0.5, 1.2, 10, 0.15, (("atr14", 1.0),)),
        HistoricalBar("2026-06-01 10:05:00", 1.2, 2.1, 1.0, 1.4, 11, 0.15, (("atr14", 1.1),)),
    ]


class ReproducibilityTests(unittest.TestCase):
    def test_same_inputs_same_versions_same_decision(self):
        def once():
            replay = HistoricalReplay(bars(), NullPredictor(), DecisionEngine(), RiskGate())
            journal = replay.run()
            return [
                (r["timestamp"], r["final_decision"], r["signal_id"], r["decision_reason"])
                for r in journal.decision_time_rows()
            ]

        self.assertEqual(once(), once())


if __name__ == "__main__":
    unittest.main()
