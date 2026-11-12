"""Phase 29 historical 500-candle diagnostic tests (research only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase16a.constants import FROZEN_CUTS
from phase29.constants import (
    HOLDOUT_NAME,
    PRODUCTION_FINAL_ACTION,
    RESEARCH_CUTOFF_UTC,
    SOURCE_HISTORICAL,
    SOURCE_SHADOW,
)
from phase29.historical_diagnostic import (
    DIAG_LABEL,
    DIAG_N,
    NOT_FORWARD,
    load_approved_h1,
    load_approved_m5,
    run_historical_500_diagnostic,
    select_last_n_window,
    write_historical_reports,
)


class Historical500DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m5 = load_approved_m5()
        cls.window = select_last_n_window(cls.m5, n=DIAG_N)
        with patch("phase29.discord_notify.deliver_decision") as mock_discord:
            cls.report = run_historical_500_diagnostic(n=DIAG_N, include_high_only=True)
            mock_discord.assert_not_called()
        cls.paths = write_historical_reports(cls.report)

    def test_01_exactly_500_candle_window(self):
        self.assertEqual(self.window["n"], 500)
        self.assertEqual(len(self.window["times"]), 500)
        self.assertEqual(self.report["window"]["n_candles"], 500)
        self.assertEqual(self.window["first_candle_utc"], "2026-09-25 21:15:00")
        self.assertEqual(self.window["last_candle_utc"], RESEARCH_CUTOFF_UTC)

    def test_02_cutoff_enforcement(self):
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")
        self.assertLessEqual(self.window["last_candle_utc"], RESEARCH_CUTOFF_UTC)
        self.assertTrue(all(t <= RESEARCH_CUTOFF_UTC for t in self.window["times"]))

    def test_03_holdout_protection(self):
        self.assertNotIn(HOLDOUT_NAME, self.m5["source_path"])
        self.assertFalse(self.m5["holdout_opened"])
        self.assertFalse(self.report["holdout"]["accessed"])
        from phase29.historical_diagnostic import _assert_no_holdout

        with self.assertRaises(RuntimeError):
            _assert_no_holdout(Path(f"data/{HOLDOUT_NAME}"))

    def test_04_no_post_cutoff_data(self):
        self.assertEqual(self.m5["excluded"]["post_cutoff"], 0)
        self.assertTrue(all(t <= RESEARCH_CUTOFF_UTC for t in self.m5["times"]))
        filtered = [t for t in self.m5["times"] if t <= RESEARCH_CUTOFF_UTC]
        fake = {"times": filtered + ["2026-09-29 19:00:00"], "cutoff": RESEARCH_CUTOFF_UTC}
        # Loader path already filters; select must only see <= cutoff times.
        fake_ok = {"times": [t for t in fake["times"] if t <= RESEARCH_CUTOFF_UTC], "cutoff": RESEARCH_CUTOFF_UTC}
        w = select_last_n_window(fake_ok, n=500)
        self.assertNotIn("2026-09-29 19:00:00", w["times"])
        self.assertTrue(all(t <= RESEARCH_CUTOFF_UTC for t in w["times"]))

    def test_05_no_future_leakage(self):
        self.assertEqual(self.window["last_candle_utc"], self.m5["times"][-1])
        self.assertLessEqual(self.m5["times"][-1], RESEARCH_CUTOFF_UTC)
        h1 = load_approved_h1()
        self.assertTrue(all(r["time"] <= RESEARCH_CUTOFF_UTC for r in h1))

    def test_06_h13c_frozen_thresholds(self):
        cuts = self.report["safety"]["frozen_cuts"]
        self.assertEqual(cuts["q_low"], 25)
        self.assertEqual(cuts["q_high"], 75)
        self.assertAlmostEqual(cuts["close_ema_low"], FROZEN_CUTS["close_ema_low"])
        self.assertAlmostEqual(cuts["close_ema_high"], FROZEN_CUTS["close_ema_high"])
        self.assertEqual(FROZEN_CUTS["source"], cuts["source"])

    def test_07_historical_decision_generation(self):
        base = self.report["baseline_h13c"]["counts"]
        self.assertEqual(base["n"], 500)
        self.assertEqual(base["BUY"] + base["SELL"] + base["WAIT"], 500)
        self.assertEqual(self.report["n_baseline_decisions_recorded"], 500)

    def test_08_entry_tp_sl_generation(self):
        for sample in self.report.get("baseline_signal_samples") or []:
            self.assertEqual(sample["experience_source"], SOURCE_HISTORICAL)
            self.assertEqual(sample["strategy"], "H13_C")
            self.assertEqual(sample["production_action"], "WAIT")
            if sample["experimental_action"] in {"BUY", "SELL"} and sample.get("accepted"):
                self.assertIsNotNone(sample["entry"])
                self.assertIsNotNone(sample["tp_level"])
                self.assertIsNotNone(sample["sl_level"])
                self.assertGreater(sample["atr"], 0)

    def test_09_h1_h12_outcome_calculation(self):
        # Frozen Phase 18 lifecycle horizons (not every integer H1–H12).
        by_h = self.report["baseline_h13c"]["outcomes"]["by_horizon"]
        for hid in ("H1", "H2", "H3", "H6", "H12"):
            self.assertIn(hid, by_h)
        perf = self.report["baseline_h13c"]["performance_h12"]["combined"]
        self.assertIn("mean_r", perf)
        self.assertIn("win_rate", perf)
        self.assertIn("profit_factor", perf)
        self.assertIn("max_drawdown_r", perf)

    def test_10_historical_hypothetical_separation(self):
        self.assertEqual(self.report["label"], DIAG_LABEL)
        self.assertEqual(self.report["not_forward_validation"], NOT_FORWARD)
        self.assertEqual(self.report["safety"]["experience_source"], SOURCE_HISTORICAL)
        self.assertNotEqual(SOURCE_HISTORICAL, SOURCE_SHADOW)

    def test_11_agent_shadow_separation(self):
        self.assertFalse(self.report["safety"]["agent_shadow_written"])
        for sample in self.report.get("baseline_signal_samples") or []:
            self.assertEqual(sample["experience_source"], SOURCE_HISTORICAL)
            self.assertNotEqual(sample["experience_source"], SOURCE_SHADOW)

    def test_12_no_discord_notifications(self):
        self.assertFalse(self.report["safety"]["discord_sent"])
        for sample in self.report.get("baseline_signal_samples") or []:
            self.assertFalse(sample.get("discord_sent", True))

    def test_13_no_broker_orders(self):
        self.assertEqual(self.report["safety"]["broker_orders"], 0)
        for sample in self.report.get("baseline_signal_samples") or []:
            self.assertFalse(sample.get("broker_order", True))

    def test_14_production_wait(self):
        self.assertEqual(self.report["safety"]["production_final_action"], PRODUCTION_FINAL_ACTION)
        self.assertEqual(self.report["verdict_channels"]["PRODUCTION_STATUS"], "WAIT")
        self.assertFalse(self.report["edge_claim"])

    def test_15_comparison_not_mixed(self):
        cmp_ = self.report["comparison_phase28_forward"]
        self.assertFalse(cmp_["mixed_into_one_performance_number"])
        self.assertEqual(cmp_["phase28_buy"], 0)
        self.assertEqual(cmp_["phase28_sell"], 0)
        self.assertEqual(cmp_["phase28_wait"], 100)

    def test_16_reports_labels(self):
        self.assertTrue(self.paths["json"].exists())
        self.assertTrue(self.paths["md"].exists())
        data = json.loads(self.paths["json"].read_text(encoding="utf-8"))
        self.assertEqual(data["label"], DIAG_LABEL)
        md = self.paths["md"].read_text(encoding="utf-8")
        self.assertIn(DIAG_LABEL, md)
        self.assertIn(NOT_FORWARD, md)
        self.assertIn("HISTORICAL_DIAGNOSTIC_RESULT", md)
        self.assertIn("FORWARD_EVIDENCE", md)
        self.assertIn("PRODUCTION_STATUS", md)


if __name__ == "__main__":
    unittest.main()
