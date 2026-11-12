"""Phase 27 unit tests."""

from __future__ import annotations

import unittest

import numpy as np

from phase27.constants import (
    H13C_Q_HIGH,
    H13C_Q_LOW,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
    VALID_VERDICTS,
)
from phase27.vol_model import assign_regime, tertile_cuts


class TestConstants(unittest.TestCase):
    def test_safety_constants(self):
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertEqual(H13C_Q_LOW, 25)
        self.assertEqual(H13C_Q_HIGH, 75)


class TestRegimes(unittest.TestCase):
    def test_tertiles_and_assign(self):
        xs = np.arange(300, dtype=float)
        lo, hi = tertile_cuts(xs)
        self.assertTrue(lo < hi)
        self.assertEqual(assign_regime(lo - 1, lo, hi), "low")
        self.assertEqual(assign_regime((lo + hi) / 2, lo, hi), "medium")
        self.assertEqual(assign_regime(hi + 1, lo, hi), "high")

    def test_verdicts(self):
        self.assertIn("VOLATILITY_PREDICTION_ONLY", VALID_VERDICTS)


if __name__ == "__main__":
    unittest.main()
