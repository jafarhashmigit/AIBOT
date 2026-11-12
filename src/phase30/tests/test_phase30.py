"""Focused Phase 30 unit tests (no holdout / MT5 / Discord)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase14.data import fold_of
from phase16a.constants import FROZEN_CUTS
from phase30.base import build_context, generate_strategy_trades
from phase30.constants import (
    HOLDOUT_NAME,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
    STRATEGY_PARAMS,
)
from phase30.integrity import verify_protected_hashes
from phase30.ranking.rank import classify_strategy, composite_rank, multiple_testing_summary, phase_verdict
from phase30.robustness.checks import permutation_test, signal_frequency_stability
from phase30.strategies import STRATEGIES
from phase30.strategies.vol_norm_momentum import decide as decide_mom


def _fake_bundle(n: int = 80) -> dict:
    from datetime import datetime, timedelta

    t0 = datetime(2026, 7, 1, 0, 0, 0)
    times = []
    features = {}
    outcomes = {}
    for i in range(n):
        t = (t0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%d %H:%M:%S")
        times.append(t)
        px = 2000 + i * 0.1
        features[t] = {
            "time": t,
            "open": px,
            "high": px + 1,
            "low": px - 1,
            "close": px + 0.2,
            "close_to_ema_20": -0.002 if i % 17 == 0 else 0.0001,
            "ema_9_20_spread": 0.0002,
            "atr_14_pct": 0.001,
            "rsi_14": 50.0,
            "volatility_12": 0.001,
            "volatility_48": 0.001,
            "volatility_ratio_12_48": 1.0,
            "corrected_session_new_york": 0,
            "corrected_session_london": 1,
            "corrected_session_asia": 0,
        }
        for side in ("BUY", "SELL"):
            outcomes[(t, side)] = {
                "net_r": 0.1 if side == "BUY" else -0.05,
                "net_pnl": 1.0 if side == "BUY" else -0.5,
                "initial_risk": 10.0,
                "costs": 0.2,
                "entry_fill": px + 0.3,
                "exit_reason": "TP" if side == "BUY" else "SL",
                "entry_time": (t0 + timedelta(minutes=5 * (i + 1))).strftime("%Y-%m-%d %H:%M:%S"),
                "exit_time": (t0 + timedelta(minutes=5 * (i + 3))).strftime("%Y-%m-%d %H:%M:%S"),
            }
    # WF2 window timestamps so fold_of works
    return {
        "timestamps": times,
        "feature_times": times,
        "feature_index": {t: i for i, t in enumerate(times)},
        "features": features,
        "outcomes": outcomes,
        "h1_rows": [
            {
                "time": (t0 + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S"),
                "open": 2000,
                "high": 2001,
                "low": 1999,
                "close": 2000.5 + h * 0.01,
            }
            for h in range(40)
        ],
        "bounds": {
            "max_decision_time": "2026-09-29 17:50:00",
            "research_cutoff": RESEARCH_CUTOFF_UTC,
            "holdout_opened": False,
        },
    }


class Phase30Tests(unittest.TestCase):
    def test_01_strategy_registry_size(self):
        self.assertEqual(len(STRATEGIES), 10)
        self.assertEqual(set(STRATEGIES), set(STRATEGY_PARAMS))

    def test_02_determinism(self):
        b = _fake_bundle()
        r1 = generate_strategy_trades(b, decide_mom, strategy_id="vol_norm_momentum")
        r2 = generate_strategy_trades(b, decide_mom, strategy_id="vol_norm_momentum")
        self.assertEqual(r1["decisions"], r2["decisions"])
        self.assertEqual(r1["n_trades"], r2["n_trades"])

    def test_03_actions_are_buy_sell_wait(self):
        b = _fake_bundle()
        for sid, decide in STRATEGIES.items():
            raw = generate_strategy_trades(b, decide, strategy_id=sid)
            for a in raw["decisions"].values():
                self.assertIn(a, {"BUY", "SELL", "WAIT"})

    def test_04_no_lookahead_context_uses_past_bars_only(self):
        b = _fake_bundle()
        t = b["timestamps"][50]
        ctx = build_context(bundle=b, decision_time=t, h1_series=[], lookback=20)
        # empty h1_series -> h1_ctx may be None; still bars end at t
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["bars"][-1]["time"], t)
        self.assertTrue(all(bar["time"] <= t for bar in ctx["bars"]))

    def test_05_entry_uses_precomputed_outcome_contract(self):
        b = _fake_bundle()
        raw = generate_strategy_trades(b, decide_mom, strategy_id="vol_norm_momentum")
        for tr in raw["trades"]:
            self.assertIn("entry_time", tr)
            self.assertGreater(tr["entry_time"], tr["decision_time"])
            self.assertIn(tr["side"], {"BUY", "SELL"})

    def test_06_wf_fold_mapping(self):
        self.assertEqual(fold_of("2026-07-01 12:00:00"), "WF1")
        self.assertEqual(fold_of("2026-08-01 12:00:00"), "WF2")
        self.assertEqual(fold_of("2026-09-01 12:00:00"), "WF3")
        self.assertIsNone(fold_of("2025-01-01 00:00:00"))

    def test_07_frozen_h13c_cuts_unchanged(self):
        self.assertEqual(FROZEN_CUTS["q_low"], 25)
        self.assertEqual(FROZEN_CUTS["q_high"], 75)

    def test_08_permutation_and_frequency(self):
        trades = [
            {"decision_time": f"2026-07-01 00:0{i}:00", "net_r": 0.2 if i % 2 == 0 else -0.1, "net_pnl": 1.0}
            for i in range(8)
        ]
        # fix timestamps
        trades = []
        for i in range(20):
            trades.append(
                {
                    "decision_time": f"2026-07-01 {i:02d}:00:00",
                    "net_r": 0.3 if i % 3 else -0.2,
                    "net_pnl": 1.0,
                }
            )
        p = permutation_test(trades, n_perm=50)
        self.assertEqual(p["status"], "COMPLETED")
        f = signal_frequency_stability({"n_decisions": 500, "n_signals": 5})
        self.assertAlmostEqual(f["signals_per_500"], 5.0)

    def test_09_ranking_and_verdict(self):
        def _metrics(mean_r, n, fold_pos=True):
            return {
                "score": {
                    "pooled": {
                        "n": n,
                        "mean_r": mean_r,
                        "median_r": mean_r,
                        "net_r": mean_r * n,
                        "profit_factor": 1.2,
                        "win_rate": 0.5,
                        "max_drawdown_usd": 10.0,
                        "bootstrap": {"ci_low": mean_r - 0.1, "ci_high": mean_r + 0.1, "p_mean_le_0": 0.2},
                    },
                    "all_active_folds_positive": fold_pos,
                },
                "cost_robustness": {"1.5x": {"mean_r": mean_r * 0.8}},
            }

        d1 = classify_strategy(
            strategy_id="a",
            metrics=_metrics(0.05, 120),
            robustness={
                "permutation": {"status": "COMPLETED", "p_value_mean_r_ge_obs": 0.02},
                "parameter_perturbation": {"status": "COMPLETED", "all_tested_positive": True},
            },
            h13c_mean_r=0.01,
            n_strategies_tested=10,
        )
        self.assertEqual(d1["status"], "RESEARCH_CANDIDATE")
        d2 = classify_strategy(
            strategy_id="b",
            metrics=_metrics(-0.05, 120),
            robustness=None,
            h13c_mean_r=0.01,
            n_strategies_tested=10,
        )
        self.assertEqual(d2["status"], "REJECTED")
        rows = [
            {"strategy_id": "a", "metrics": _metrics(0.05, 120), "decision": d1, "robustness": None},
            {"strategy_id": "b", "metrics": _metrics(-0.05, 120), "decision": d2, "robustness": None},
        ]
        ranked = composite_rank(rows)
        self.assertEqual(ranked[0]["strategy_id"], "a")
        mt = multiple_testing_summary({"a": d1, "b": d2})
        self.assertEqual(mt["n_strategies_tested"], 2)
        self.assertEqual(phase_verdict({"a": d1, "b": d2}), "RESEARCH_CANDIDATE_FOUND")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")

    def test_10_protected_hashes_and_holdout_name(self):
        h = verify_protected_hashes()
        self.assertTrue(h["all_ok"])
        self.assertEqual(HOLDOUT_NAME, "xauusd_m5_test.csv")
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")

    def test_11_vs_phase25_documented(self):
        for sid, p in STRATEGY_PARAMS.items():
            self.assertIn("vs_phase25", p)
            self.assertTrue(len(str(p["vs_phase25"])) > 10)


if __name__ == "__main__":
    unittest.main()
