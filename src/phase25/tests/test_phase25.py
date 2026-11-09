"""Phase 25 unit tests — offline, no network required for core logic."""

from __future__ import annotations

import math
import unittest

from phase25.constants import STRATEGY_PARAMS, VALID_STATUSES
from phase25.evaluate import classify_strategy
from phase25.indicators import bearish_fvg, bullish_fvg, donchian, swing_points, zscore
from phase25.strategies.breakout_retest import decide_breakout_retest
from phase25.strategies.mean_reversion import decide_mean_reversion
from phase25.strategies.mtf_h1_m5 import decide_mtf_h1_m5
from phase25.strategies.regime_router import classify_regime, decide_regime_router
from phase25.strategies.smc_liquidity import decide_smc_liquidity


def _bar(o, h, l, c, **extra):
    d = {
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "atr_14_pct": 0.001,
        "rsi_14": 50,
        "ema_9_20_spread": 0.0,
        "close_to_ema_20": 0.0,
        "volatility_ratio_12_48": 1.0,
        "corrected_session_new_york": 0,
    }
    d.update(extra)
    return d


class TestIndicators(unittest.TestCase):
    def test_zscore_zero_at_mean(self):
        vals = [1.0] * 40
        self.assertEqual(zscore(vals, 40), 0.0)

    def test_donchian_excludes_current(self):
        highs = [1, 2, 3, 10]
        lows = [0, 0, 0, -1]
        u, l = donchian(highs, lows, 3)
        self.assertEqual(u, 3)
        self.assertEqual(l, 0)

    def test_swing_requires_right_bars(self):
        h = [1, 2, 5, 2, 1]
        l = [0, 0, 0, 0, 0]
        sh, _ = swing_points(h, l, lookback=2)
        self.assertEqual(sh, [(2, 5.0)])

    def test_fvg(self):
        bars = [_bar(1, 1.0, 0.9, 0.95), _bar(1, 1.1, 1.0, 1.05), _bar(1, 1.4, 1.25, 1.3)]
        self.assertTrue(bullish_fvg(bars, min_gap=0.2))
        bars2 = [_bar(1, 1.4, 1.3, 1.35), _bar(1, 1.2, 1.1, 1.15), _bar(1, 1.05, 0.9, 0.95)]
        self.assertTrue(bearish_fvg(bars2, min_gap=0.2))


class TestStrategies(unittest.TestCase):
    def test_mean_reversion_buy(self):
        bars = [_bar(100, 101, 99, 100 + i * 0.01) for i in range(39)]
        bars.append(_bar(100, 101, 90, 90, rsi_14=20, atr_14_pct=0.001))
        action, reason = decide_mean_reversion({"feat": bars[-1], "bars": bars, "h1_ctx": {}})
        self.assertEqual(action, "BUY")
        self.assertIn("buy", reason)

    def test_mtf_requires_h1(self):
        feat = _bar(1, 1, 1, 1, rsi_14=40, ema_9_20_spread=0.001)
        a, r = decide_mtf_h1_m5({"feat": feat, "bars": [feat], "h1_ctx": None})
        self.assertEqual(a, "WAIT")
        self.assertEqual(r, "missing_h1")

    def test_regime_high_vol(self):
        feat = _bar(1, 1, 1, 1, atr_14_pct=0.01, ema_9_20_spread=0.0)
        self.assertEqual(classify_regime(feat), "high_vol")

    def test_params_predeclared(self):
        self.assertEqual(set(STRATEGY_PARAMS), {
            "mean_reversion",
            "breakout_retest",
            "smc_liquidity",
            "regime_router",
            "mtf_h1_m5",
        })


class TestClassify(unittest.TestCase):
    def test_statuses_valid(self):
        score = {
            "pooled": {
                "n": 5,
                "mean_r": 0.1,
                "n_days": 3,
                "bootstrap": {"ci_low": -0.1, "ci_high": 0.2},
            },
            "all_active_folds_positive": False,
        }
        cost = {"1.5x": {"mean_r": 0.05}}
        d = classify_strategy(score=score, cost=cost, h13c_mean_r=0.01, strategy_id="x")
        self.assertIn(d["status"], VALID_STATUSES)
        self.assertFalse(d["production_ready"])


if __name__ == "__main__":
    unittest.main()
