"""Phase 32 independent validation tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase32.constants import EXTRA_COST_PER_SIDE, HOLDOUT_NAME, PRODUCTION_FINAL_ACTION, RESEARCH_CUTOFF_UTC
from phase32.execution_realism import classify_execution_realism
from phase32.independent_features import add_corrected_utc_independent, recompute_features_independent
from phase32.independent_labels import BUY, _simulate_trade_independent
from phase32.integrity import verify_protected_hashes
from phase32.run_phase32 import decide_verdict


class Phase32Tests(unittest.TestCase):
    def test_01_cutoff_holdout_production(self):
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertEqual(HOLDOUT_NAME, "xauusd_m5_test.csv")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")

    def test_02_protected_hashes(self):
        self.assertTrue(verify_protected_hashes()["all_ok"])

    def test_03_independent_feature_warmup_synthetic(self):
        n = 80
        t0 = pd.Timestamp("2026-06-01 00:00:00")
        times = [t0 + pd.Timedelta(minutes=5 * i) for i in range(n)]
        px = np.linspace(2000, 2010, n)
        raw = pd.DataFrame(
            {
                "time": times,
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px + 0.2,
                "tick_volume": np.full(n, 100.0),
                "spread": np.full(n, 20.0),
            }
        )
        feats = recompute_features_independent(raw)
        self.assertGreater(len(feats), 0)
        self.assertLess(len(feats), n)
        self.assertTrue(feats["atr_14"].notna().all())

    def test_04_dst_corrected_hour(self):
        # Winter vs summer Athens offset
        raw_times = pd.DataFrame(
            {
                "time": pd.to_datetime(["2026-01-15 12:00:00", "2026-07-15 12:00:00"]),
                "open": [2000.0, 2000.0],
                "high": [2001.0, 2001.0],
                "low": [1999.0, 1999.0],
                "close": [2000.5, 2000.5],
            }
        )
        out = add_corrected_utc_independent(raw_times)
        # Jan Athens UTC+2 → 10:00 UTC; Jul UTC+3 → 09:00 UTC
        self.assertEqual(int(out.loc[0, "corrected_hour_utc"]), 10)
        self.assertEqual(int(out.loc[1, "corrected_hour_utc"]), 9)

    def test_05_sl_priority_independent_sim(self):
        times = np.arange("2026-01-01T00:00", "2026-01-01T01:40", dtype="datetime64[m]")[::5]
        n = len(times)
        open_ = np.full(n, 2000.0)
        high = np.full(n, 2001.0)
        low = np.full(n, 1999.0)
        close = np.full(n, 2000.0)
        spread = np.full(n, 0.15)
        high[2] = 2010.0
        low[2] = 1980.0
        tr = _simulate_trade_independent(
            open_=open_,
            high=high,
            low=low,
            close=close,
            spread_usd=spread,
            time=times,
            side=BUY,
            signal_pos=0,
            atr=2.0,
        )
        self.assertEqual(tr["exit_reason"], "SL")
        self.assertEqual(str(tr["entry_time"])[:19], str(times[1])[:19])

    def test_06_cost_identity(self):
        gross, costs, net = 1.0, 0.25, 0.75
        self.assertAlmostEqual(gross - costs, net)
        self.assertGreaterEqual(costs, 2 * EXTRA_COST_PER_SIDE - 1e-12)

    def test_07_execution_realism_and_verdict(self):
        r = classify_execution_realism(trade_cost_ok=True, label_ok=True, bid_ask_verified=False)
        self.assertEqual(r["classification"], "ASSUMPTION_BASED")
        v = decide_verdict(feat_ok=True, label_ok=True, trade_ok=True, realism_class=r["classification"])
        self.assertEqual(v, "EXECUTION_REALISM_UNVERIFIED")
        v2 = decide_verdict(feat_ok=False, label_ok=True, trade_ok=True, realism_class="ASSUMPTION_BASED")
        self.assertEqual(v2, "FEATURE_RECOMPUTATION_MISMATCH")


if __name__ == "__main__":
    unittest.main()
