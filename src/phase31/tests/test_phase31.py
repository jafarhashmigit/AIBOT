"""Focused Phase 31 forensic tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase14.data import fold_of
from phase18.barrier import simulate_trade_horizon
from phase31.constants import HOLDOUT_NAME, PRODUCTION_FINAL_ACTION, RESEARCH_CUTOFF_UTC
from phase31.integrity import verify_protected_hashes
from phase31.statistical_audit import benjamini_hochberg, block_bootstrap_mean, holm_bonferroni, iid_bootstrap_mean


class Phase31Tests(unittest.TestCase):
    def test_01_cutoff_and_holdout_name(self):
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertEqual(HOLDOUT_NAME, "xauusd_m5_test.csv")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")

    def test_02_protected_hashes(self):
        self.assertTrue(verify_protected_hashes()["all_ok"])

    def test_03_wf_fold_order(self):
        self.assertEqual(fold_of("2026-07-01 12:00:00"), "WF1")
        self.assertEqual(fold_of("2026-08-01 12:00:00"), "WF2")
        self.assertEqual(fold_of("2026-09-01 12:00:00"), "WF3")

    def test_04_same_candle_sl_priority(self):
        times = np.arange("2026-01-01T00:00", "2026-01-01T01:40", dtype="datetime64[m]")[::5]
        n = len(times)
        open_ = np.full(n, 2000.0)
        high = np.full(n, 2001.0)
        low = np.full(n, 1999.0)
        close = np.full(n, 2000.0)
        spread = np.full(n, 0.15)
        high[2] = 2010.0
        low[2] = 1980.0
        m = {"time": times, "open": open_, "high": high, "low": low, "close": close, "spread": spread}
        buy = simulate_trade_horizon(m, 1, 0, atr=2.0, horizon_bars=12)
        self.assertEqual(buy["exit_reason"], "SL")
        self.assertEqual(str(buy["entry_time"])[:19], str(times[1])[:19])

    def test_05_bootstrap_helpers(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, size=200)
        iid = iid_bootstrap_mean(x, n_samples=100)
        blk = block_bootstrap_mean(x, block=10, n_samples=100)
        self.assertIn("ci_low", iid)
        self.assertIn("ci_high", blk)
        self.assertLessEqual(iid["ci_low"], iid["ci_high"])

    def test_06_multiple_testing_helpers(self):
        p = [0.001, 0.04, 0.2]
        h = holm_bonferroni(p, alpha=0.05)
        b = benjamini_hochberg(p, alpha=0.05)
        self.assertEqual(len(h), 3)
        self.assertTrue(h[0]["reject"])
        self.assertEqual(len(b), 3)

    def test_07_preflight_phase30_figures(self):
        from phase31.preflight import run_preflight

        pre = run_preflight()
        self.assertTrue(pre["safety"]["protected_artifacts_intact"])
        self.assertTrue(pre["safety"]["cutoff_ok"])
        if pre.get("phase30_verification"):
            self.assertTrue(pre["phase30_verification"]["all_verified"])


if __name__ == "__main__":
    unittest.main()
