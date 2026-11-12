"""Phase51 frozen confirmation tests."""

from __future__ import annotations

import unittest

from phase44.constants import DISCOVERY_DATES, VALIDATION_DATES
from phase51.candidate import FrozenAIBOTCandidate
from phase51.constants import canonical_json_sha256
from phase51.date_selection import blocked_dates, freeze_date_selection, remaining_pool
from phase51.freeze import freeze_phase50_learner
from phase51.qualification import choose_verdict


class TestFreeze(unittest.TestCase):
    def test_freeze_hash_stable(self) -> None:
        a = freeze_phase50_learner()
        body = {k: v for k, v in a.items() if k != "frozen_learner_sha256"}
        self.assertEqual(a["frozen_learner_sha256"], canonical_json_sha256(body))
        self.assertTrue(a["no_modification_allowed"])


class TestDates(unittest.TestCase):
    def test_excludes_prior_phases(self) -> None:
        blocked = blocked_dates()
        self.assertTrue(set(DISCOVERY_DATES).issubset(blocked))
        self.assertTrue(set(VALIDATION_DATES).issubset(blocked))
        pool = remaining_pool()
        self.assertFalse(set(pool) & blocked)
        sel = freeze_date_selection()
        self.assertFalse(set(sel["selected_dates"]) & blocked)
        self.assertEqual(sel["selection_sha256"], canonical_json_sha256({k: v for k, v in sel.items() if k != "selection_sha256"}))


class TestCandidate(unittest.TestCase):
    def test_decide_wait_empty_exp(self) -> None:
        c = FrozenAIBOTCandidate("deadbeef")
        out = c.decide(
            {"timestamp_utc": "2025-07-04 12:00:00", "features": {"E02_spread_atr": 0.01, "D03_overlap": 1.0, "C03_vol_accel": 1.0}},
            {"HISTORICAL_HYPOTHETICAL": [], "AGENT_SHADOW": []},
        )
        self.assertEqual(out["action"], "WAIT")
        self.assertTrue(out["paper_only"])
        self.assertIn(out["action"], ("BUY", "SELL", "WAIT"))


class TestVerdict(unittest.TestCase):
    def test_fail_default(self) -> None:
        v, _ = choose_verdict(
            {
                "frozen_summary": {"mean_net_r": -0.1, "incremental_value_vs_baseline": -0.1, "block_rows": []},
                "wait_summary": {},
                "const_buy_summary": {"mean_net_r": 0},
                "const_sell_summary": {"mean_net_r": 0},
                "controls": {"randomized": {"incremental_value_vs_baseline": 0}},
                "leakage_ok": True,
                "no_tuning": True,
            }
        )
        self.assertEqual(v, "INDEPENDENT_CONFIRMATION_FAILED")


if __name__ == "__main__":
    unittest.main()
