"""Phase 26 unit tests (offline)."""

from __future__ import annotations

import unittest

import numpy as np

from phase26.constants import (
    HORIZONS,
    ORTHOGONAL_CANDIDATES,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
    VALID_VERDICTS,
)
from phase26.evaluate import decide_verdict
from phase26.outcomes import build_rich_outcomes


class TestConstants(unittest.TestCase):
    def test_cutoff_and_wait(self):
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertIn(12, HORIZONS)

    def test_candidates_nonempty(self):
        self.assertGreaterEqual(len(ORTHOGONAL_CANDIDATES), 10)


class TestOutcomes(unittest.TestCase):
    def test_mfe_mae_not_confused_with_net_r(self):
        n = 40
        close = np.linspace(100, 110, n)
        feats = {
            "_open": close.copy(),
            "_high": close + 1.0,
            "_low": close - 1.0,
            "_close": close,
            "_atr": np.ones(n),
            "_atr_pct": np.full(n, 0.01),
            "_gap": np.zeros(n),
            "_minutes_gap": np.full(n, 5.0),
        }
        out = build_rich_outcomes(feats, n)
        # With high=close+1 and atr=1, BUY MFE over H=3 near 1.0 ATR scale
        self.assertTrue(np.nanmean(out["mfe_buy_atr"][3]) > 0)
        self.assertTrue(np.nanmean(out["mae_buy_atr"][3]) > 0)
        # labels exist separately
        self.assertIn(3, out["mfe_buy_atr"])
        self.assertIn(3, out["fwd_ret_buy"])


class TestVerdict(unittest.TestCase):
    def test_no_accepted_features(self):
        v = decide_verdict({"accepted": [], "rejected": ["x"]}, {})
        self.assertEqual(v["verdict"], "NO_INCREMENTAL_INFORMATION")
        self.assertIn(v["verdict"], VALID_VERDICTS)
        self.assertFalse(v["production_ready"])


if __name__ == "__main__":
    unittest.main()
