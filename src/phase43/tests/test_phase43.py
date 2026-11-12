"""Phase 43 tests — exposure classification and policy (no MT5 required)."""

from __future__ import annotations

import unittest

from phase43.constants import CHAMPION_STATUS, PRODUCTION_FINAL_ACTION, RECIPE_ID, WINDOW_END, WINDOW_START
from phase43.exposure import classify_day, select_unseen_dates
from phase43.qualification import decide_verdict


class TestPolicy(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase43_"))
        self.assertEqual(WINDOW_START.isoformat(), "2025-07-02")
        self.assertEqual(WINDOW_END.isoformat(), "2026-02-15")


class TestExposure(unittest.TestCase):
    def test_known_eval_exposed(self):
        row = classify_day("2025-08-15", {}, set())
        self.assertEqual(row["exposure_class"], "PREVIOUSLY_EXPOSED")
        self.assertFalse(row["independent_validation_eligibility"])

    def test_unseen(self):
        row = classify_day("2025-07-09", {}, set())
        self.assertEqual(row["exposure_class"], "UNSEEN")
        self.assertTrue(row["independent_validation_eligibility"])

    def test_h1_neighbor_partial(self):
        row = classify_day("2025-08-14", {}, {"2025-08-14"})
        self.assertEqual(row["exposure_class"], "PARTIALLY_EXPOSED")

    def test_selection_deterministic(self):
        exposure = {
            "in_window_rows": [
                {"date": f"2025-07-{d:02d}", "exposure_class": "UNSEEN", "independent_validation_eligibility": True}
                for d in range(2, 20)
                if __import__("datetime").date(2025, 7, d).weekday() < 5
            ]
        }
        a = select_unseen_dates(exposure, k=5)
        b = select_unseen_dates(exposure, k=5)
        self.assertEqual(a["selected_dates"], b["selected_dates"])


class TestVerdict(unittest.TestCase):
    def test_no_independent(self):
        v = decide_verdict(
            exposure={"summary": {"n_unseen": 0}},
            selection={"selected_n": 0},
            acquisition={"completed_dates": [], "pending_dates": [], "stop_reason": None},
            quality={"n_complete_sessions": 0, "n_h1_warmup_ok": 0},
            indep_ok=True,
            eligibility={"A_n": 0},
        )
        self.assertEqual(v["final_verdict"], "NO_INDEPENDENT_DATA_AVAILABLE")


if __name__ == "__main__":
    unittest.main()
