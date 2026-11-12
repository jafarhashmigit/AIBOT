"""Phase49 tests — design integrity (no confirmation peeking)."""

from __future__ import annotations

import unittest

from phase49.constants import FORBIDDEN_VALIDATION_DATES, HORIZON_BARS, N_CONFIRMATION, N_DISCOVERY
from phase49.date_selection import freeze_date_selection, remaining_unseen_pool, select_evenly
from phase49.independent import verify_selection
from phase49.qualification import choose_verdict
from phase49.registry import build_feature_registry, build_hypothesis_registry


class TestDateSelection(unittest.TestCase):
    def test_pool_excludes_forbidden_and_prior(self) -> None:
        meta = remaining_unseen_pool()
        self.assertGreater(meta["pool_n"], 40)
        self.assertFalse(set(meta["pool"]) & FORBIDDEN_VALIDATION_DATES)

    def test_even_selection_deterministic(self) -> None:
        meta = remaining_unseen_pool()
        a = select_evenly(meta["pool"], 40)
        b = select_evenly(meta["pool"], 40)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 40)
        self.assertFalse(set(a) & FORBIDDEN_VALIDATION_DATES)

    def test_freeze_split_and_hash(self) -> None:
        sel = freeze_date_selection()
        self.assertEqual(len(sel["discovery_dates"]), N_DISCOVERY)
        self.assertEqual(len(sel["confirmation_dates"]), N_CONFIRMATION)
        self.assertTrue(max(sel["discovery_dates"]) < min(sel["confirmation_dates"]))
        self.assertTrue(verify_selection(sel)["ok"])


class TestRegistry(unittest.TestCase):
    def test_limits(self) -> None:
        fr = build_feature_registry()
        hr = build_hypothesis_registry()
        self.assertLessEqual(fr["n_features"], 30)
        self.assertEqual(fr["n_features"], 30)
        self.assertLessEqual(hr["n_hypotheses"], 18)
        self.assertEqual(hr["n_hypotheses"], 18)
        self.assertFalse(fr["vwap_included"])


class TestOverlapLogic(unittest.TestCase):
    def test_stride_nonoverlap(self) -> None:
        # decisions at 48, 60, 72... exits at decision+12
        idxs = list(range(48, 200, 12))
        for a, b in zip(idxs, idxs[1:]):
            self.assertGreaterEqual(b, a + HORIZON_BARS)


class TestVerdict(unittest.TestCase):
    def test_no_survivor(self) -> None:
        v, _ = choose_verdict(
            {
                "acquisition": {"completed_dates": ["x"] * 25},
                "discovery": {"n_survivors": 0, "survivors": []},
                "confirmation": {"opened": False},
            }
        )
        self.assertEqual(v, "NO_INFORMATION_FAMILY_FOUND")


if __name__ == "__main__":
    unittest.main()
