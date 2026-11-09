"""Phase 13 unit tests. Synthetic fixtures + integrity. No holdout. No MT5."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta

from phase13.constants import GAP_MIN, HYPOTHESIS_IDS, MAX_DECISION_TIME, RESEARCH_CUTOFF_UTC
from phase13.evaluate import assign_status, bh_fdr, score_policy
from phase13.experience_audit import experience_source_audit
from phase13.h1_context import build_h1_lookup, h1_context_at
from phase13.hypotheses import (
    signal_breakout_failure,
    signal_e1,
    signal_pred_gap_midvol,
    signal_vol_expansion_trend,
)
from phase13.integrity import snapshot_all
from phase13.inventory import research_inventory


def _ts(start: str, i: int) -> str:
    dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=5 * i)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _mini_bundle() -> dict:
    """Synthetic research slice. Not live data. Not holdout."""
    start = "2026-06-19 03:05:00"
    feature_times = [_ts(start, i) for i in range(40)]
    features = {}
    for i, t in enumerate(feature_times):
        features[t] = {
            "time": t,
            "open": 4000 + i * 0.1,
            "high": 4000 + i * 0.1 + 2.0,
            "low": 4000 + i * 0.1 - 2.0,
            "close": 4000 + i * 0.1 + 0.2,
            "atr_14_pct": 0.001 if i < 30 else 0.01,
            "ema_9_20_spread": 1.0 if i % 2 == 0 else -1.0,
            "ema_20_50_spread": 1.0 if i % 2 == 0 else -1.0,
            "close_to_ema_20": -0.5 if i % 2 == 0 else 0.5,
            "corrected_session_new_york": 0,
        }
    # Make a clear upside failure on last bar
    t_fail = feature_times[-1]
    prior_high = max(float(features[feature_times[j]]["high"]) for j in range(len(feature_times) - 13, len(feature_times) - 1))
    features[t_fail]["high"] = prior_high + 1.0
    features[t_fail]["close"] = prior_high - 0.5
    features[t_fail]["atr_14_pct"] = 0.0005

    outcomes = {}
    oos = {}
    for t in feature_times[20:]:
        outcomes[(t, "BUY")] = {"net_r": -0.1, "net_pnl": -1.0, "initial_risk": 2.0, "costs": 0.25}
        outcomes[(t, "SELL")] = {"net_r": 0.05, "net_pnl": 0.5, "initial_risk": 2.0, "costs": 0.25}
        oos[t] = {
            "fold_id": "WF1",
            "pred_r_rf": {"BUY": 0.1, "SELL": -0.05},
            "actual_net_r": {"BUY": -0.1, "SELL": 0.05},
            "actual_net_pnl": {"BUY": -1.0, "SELL": 0.5},
        }
    return {
        "features": features,
        "feature_times": feature_times,
        "feature_index": {t: i for i, t in enumerate(feature_times)},
        "outcomes": outcomes,
        "oos": oos,
        "timestamps": feature_times[20:],
        "h1_rows": [
            {
                "time": _ts("2026-06-18 00:00:00", i * 12),
                "open": 4000,
                "high": 4010,
                "low": 3990,
                "close": 4000 + i,
            }
            for i in range(30)
        ],
    }


class Phase13Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_01_inventory_lists_ny_sell_as_do_not_repeat(self):
        inv = research_inventory()
        self.assertTrue(any(x["id"] == "P5_NY_SELL_REPLICATION" for x in inv["tested_hypotheses"]))
        self.assertIn("Unconditional corrected-NY SELL", inv["do_not_repeat_without_improvement"])

    def test_02_four_pre_registered_hypothesis_ids(self):
        self.assertEqual(len(HYPOTHESIS_IDS), 4)
        self.assertIn("H13_A_BREAKOUT_FAILURE", HYPOTHESIS_IDS)

    def test_03_breakout_failure_emits_sell_on_failed_high(self):
        bundle = _mini_bundle()
        cuts = {"atr_p33": 0.001, "atr_p67": 0.005, "close_ema_p25": -0.2, "close_ema_p75": 0.2}
        t = bundle["feature_times"][-1]
        self.assertEqual(signal_breakout_failure(bundle, t, cuts, 12), "SELL")

    def test_04_vol_expansion_trend_requires_high_atr(self):
        bundle = _mini_bundle()
        cuts = {"atr_p33": 0.001, "atr_p67": 0.005, "close_ema_p25": -0.2, "close_ema_p75": 0.2}
        t_low = bundle["feature_times"][25]
        bundle["features"][t_low]["atr_14_pct"] = 0.001
        self.assertEqual(signal_vol_expansion_trend(bundle, t_low, cuts), "WAIT")
        bundle["features"][t_low]["atr_14_pct"] = 0.01
        bundle["features"][t_low]["ema_9_20_spread"] = 1.0
        bundle["features"][t_low]["ema_20_50_spread"] = 1.0
        self.assertEqual(signal_vol_expansion_trend(bundle, t_low, cuts), "BUY")

    def test_05_pred_gap_filter_waits_on_small_gap(self):
        bundle = _mini_bundle()
        cuts = {"atr_p33": 0.0, "atr_p67": 1.0, "close_ema_p25": -1, "close_ema_p75": 1}
        t = bundle["timestamps"][0]
        bundle["oos"][t]["pred_r_rf"] = {"BUY": 0.01, "SELL": 0.0}
        self.assertLess(abs(0.01 - 0.0), GAP_MIN)
        self.assertEqual(signal_pred_gap_midvol(bundle, t, cuts), "WAIT")
        bundle["oos"][t]["pred_r_rf"] = {"BUY": 0.2, "SELL": -0.1}
        self.assertEqual(signal_pred_gap_midvol(bundle, t, cuts), "BUY")

    def test_06_e1_baseline_matches_max_positive_side(self):
        bundle = _mini_bundle()
        t = bundle["timestamps"][0]
        self.assertEqual(signal_e1(bundle, t), "BUY")
        bundle["oos"][t]["pred_r_rf"] = {"BUY": -0.1, "SELL": -0.2}
        self.assertEqual(signal_e1(bundle, t), "WAIT")

    def test_07_h1_context_uses_only_closed_bars(self):
        base = datetime(2026, 6, 18, 0, 0, 0)
        rows = []
        for h in range(48):
            t = base + timedelta(hours=h)
            rows.append({
                "time": t.strftime("%Y-%m-%d %H:%M:%S"),
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.0 + h * 0.01,
            })
        lookup = build_h1_lookup(rows)
        # At 2026-06-19 10:30, last closed H1 is 09:00 (closes 10:00)
        ctx = h1_context_at(lookup, "2026-06-19 10:30:00")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["h1_bar_time"], "2026-06-19 09:00:00")
        # At 09:30, 09:00 bar not closed yet → 08:00
        ctx2 = h1_context_at(lookup, "2026-06-19 09:30:00")
        self.assertEqual(ctx2["h1_bar_time"], "2026-06-19 08:00:00")

    def test_08_wait_is_legitimate_and_scored(self):
        bundle = _mini_bundle()
        decisions = {t: "WAIT" for t in bundle["timestamps"]}
        score = score_policy(bundle, decisions, label="WAIT_TEST")
        self.assertEqual(score["n_trades"], 0)
        self.assertEqual(score["n_wait"], len(bundle["timestamps"]))

    def test_09_bh_fdr_helper(self):
        out = bh_fdr([("a", 0.001), ("b", 0.2), ("c", 0.3)], q=0.1)
        self.assertEqual(out["m"], 3)
        self.assertIn("a", out["discoveries"])

    def test_10_assign_status_rejects_negative(self):
        fake = {
            "policy_id": "H13_B_VOL_EXPANSION_TREND",
            "n_trades": 200,
            "pooled": {
                "n": 200,
                "mean_r": -0.05,
                "profit_factor": 0.9,
                "bootstrap": {"ci_low": -0.1, "ci_high": 0.0, "p_mean_le_0": 0.9},
            },
            "cost_stress": {"1.5x": {"mean_r": -0.08}},
            "all_active_folds_positive": False,
            "majority_folds_positive": False,
        }
        assigned = assign_status(fake, fdr_pass=False, sensitivity_ok=True, h1_coverage_ok=True)
        self.assertEqual(assigned["status"], "REJECTED")

    def test_11_experience_sources_not_combined(self):
        audit = experience_source_audit()
        self.assertFalse(audit["combined_learner"]["implemented"])
        self.assertEqual(audit["agent_paper"]["completed_paper_trades"], 0)
        self.assertFalse(audit["agent_paper"]["fabricated"])

    def test_12_cutoff_constants(self):
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertEqual(MAX_DECISION_TIME, "2026-09-29 17:50:00")
        self.assertLess(MAX_DECISION_TIME, RESEARCH_CUTOFF_UTC)

    def test_13_protected_hashes_unchanged(self):
        snap = snapshot_all()
        self.assertTrue(all(v["unchanged"] for v in snap["phase_1_11"].values()))
        self.assertTrue(all(v["unchanged"] for v in snap["phase_12_12b"].values()))
        self.assertTrue(all(v["unchanged"] for v in snap["phase_12c"].values()))
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_14_no_future_timestamp_in_synthetic_signals(self):
        bundle = _mini_bundle()
        for t in bundle["timestamps"]:
            self.assertLessEqual(t, MAX_DECISION_TIME)


if __name__ == "__main__":
    unittest.main()
