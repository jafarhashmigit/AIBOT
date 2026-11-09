import json
import unittest

from phase8.experience_schema import outcome_end_for
from phase8.replay import replay
from phase8.tests.factories import decision


def _row(ts: str, fold: str = "WF1") -> dict:
    third = 1.0 / 3.0
    pred = {
        "buy": {"tp": third, "sl": third, "time": third},
        "sell": {"tp": third, "sl": third, "time": third},
        "expected_buy_r": 0.0,
        "expected_sell_r": 0.0,
        "predictor_version": "test",
    }
    return {
        "decision_id": f"{ts}_XAUUSD_M5",
        "timestamp": ts,
        "fold_id": fold,
        "model_id": "phase2_rf_oos",
        "prediction": json.dumps(pred),
        "uncertainty": json.dumps({"method": "none", "buy": 0.0, "sell": 0.0}),
        "estimated_cost": 0.25,
        "raw_decision": "WAIT",
        "final_decision": "WAIT",
    }


def _ev(ts: str) -> dict:
    return {
        "timestamp": ts,
        "actual_net_r_BUY": -1.0,
        "actual_net_pnl_BUY": -2.0,
        "actual_exit_reason_BUY": "SL",
        "actual_net_r_SELL": 1.5,
        "actual_net_pnl_SELL": 3.0,
        "actual_exit_reason_SELL": "TP",
    }


class ReplayChronoTests(unittest.TestCase):
    def test_e_no_preload(self):
        stamps = [
            "2026-06-19 10:00:00",
            "2026-06-19 10:05:00",
            "2026-06-19 11:00:00",
            "2026-06-19 11:05:00",
        ]
        rows = [_row(t) for t in stamps]
        ev = {t: _ev(t) for t in stamps}
        result = replay(rows, ev, use_experience=True)
        n_at = {r["timestamp"]: r["experience_n"] for r in result["records"]}
        self.assertEqual(n_at["2026-06-19 10:00:00"], 0)
        self.assertEqual(n_at["2026-06-19 10:05:00"], 0)
        # 10:00 experience completes at 11:00, visible only after 11:00
        self.assertEqual(n_at["2026-06-19 11:00:00"], 0)
        self.assertEqual(n_at["2026-06-19 11:05:00"], 1)
        self.assertEqual(result["n_leakage"], 0)

    def test_replay_final_is_wait(self):
        rows = [_row("2026-06-19 10:00:00"), _row("2026-06-19 10:05:00")]
        ev = {r["timestamp"]: _ev(r["timestamp"]) for r in rows}
        result = replay(rows, ev, use_experience=True)
        self.assertTrue(all(r["final_decision"] == "WAIT" for r in result["records"]))

    def test_g_observation_has_no_outcomes(self):
        from phase8.replay import _observation
        mapping = _observation("2026-06-19 10:00:00").to_mapping()
        self.assertNotIn("realized_R", mapping)
        self.assertNotIn("actual_net_r", mapping)
        self.assertNotIn("hypothetical_buy_net_r", mapping)

    def test_f_replay_deterministic(self):
        rows = [_row("2026-06-19 10:00:00"), _row("2026-06-19 11:05:00")]
        ev = {r["timestamp"]: _ev(r["timestamp"]) for r in rows}
        a = replay(rows, ev, use_experience=True)
        b = replay(rows, ev, use_experience=True)
        self.assertEqual([r["experience_n"] for r in a["records"]], [r["experience_n"] for r in b["records"]])
        self.assertEqual(a["experience_ids"], b["experience_ids"])

    def test_outcome_end_helper(self):
        self.assertEqual(outcome_end_for("2026-06-19 10:00:00"), "2026-06-19 11:00:00")
        _ = decision("2026-06-19 10:00:00")


if __name__ == "__main__":
    unittest.main()
