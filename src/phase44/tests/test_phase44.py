"""Phase 44 tests — allocation lock, hypothesis distinctness, policy."""

from __future__ import annotations

import unittest

from phase44.constants import (
    CHAMPION_STATUS,
    DISCOVERY_DATES,
    PHASE42_REJECTED_PREFIX,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    VALIDATION_DATES,
)
from phase44.hypotheses import primary_hypotheses
from phase44.qualification import decide_verdict
from phase44.triggers import detect_events


class TestPolicy(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase44_"))
        self.assertEqual(len(DISCOVERY_DATES), 15)
        self.assertEqual(len(VALIDATION_DATES), 15)
        self.assertEqual(len(set(DISCOVERY_DATES) & set(VALIDATION_DATES)), 0)


class TestHypotheses(unittest.TestCase):
    def test_five_distinct(self):
        hyps = primary_hypotheses()
        self.assertEqual(len(hyps), 5)
        ids = [h["id"] for h in hyps]
        self.assertEqual(len(ids), len(set(ids)))
        for hid in ids:
            self.assertFalse(hid.startswith(PHASE42_REJECTED_PREFIX))
            self.assertTrue(hid.startswith("H44_"))


class TestTriggers(unittest.TestCase):
    def test_continuation(self):
        rows = [
            {
                "time": "2025-07-02 12:00:00",
                "day": "2025-07-02",
                "bar_disp_atr": 2.0,
                "close_aligned": True,
                "disp_sign": 1,
                "atr_14": 1.0,
                "close": 100.0,
            }
        ]
        ev = detect_events("H44_2_DISPLACEMENT_CONTINUATION", rows)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["side"], 1)


class TestVerdict(unittest.TestCase):
    def test_no_survivors(self):
        v = decide_verdict(
            {"results": [{"hypothesis_id": "x"}], "survivor_ids": [], "rejected": [{"hypothesis_id": "x"}]},
            None,
            indep_ok=True,
            preflight_ok=True,
        )
        self.assertEqual(v["final_verdict"], "NO_PREDICTIVE_VALUE")


if __name__ == "__main__":
    unittest.main()
