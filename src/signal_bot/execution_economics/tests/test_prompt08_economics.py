"""Prompt8 economics, spread, cost, sensitivity, qualification, safety tests."""

from __future__ import annotations

import unittest

from signal_bot.execution_economics.constants import (
    CHAMPION_STATUS,
    COST_MODEL_VERSION,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    UNKNOWN,
    VERIFIED,
)
from signal_bot.execution_economics.cost_model import apply_costs_to_trade_r, build_cost_model
from signal_bot.execution_economics.c07_readiness import build_c07_a_readiness
from signal_bot.execution_economics.collector_reliability import (
    inspect_collector_reliability,
    write_autostart_script,
)
from signal_bot.execution_economics.quote_validation import validate_quote_record
from signal_bot.execution_economics.sensitivity import evaluate_trade_cost_sensitivity
from signal_bot.execution_economics.spread_analysis import analyze_live_spreads
from signal_bot.execution_economics.evidence_qualification import build_live_evidence_qualification


class TestQuoteValidation(unittest.TestCase):
    def _base(self, **kw):
        q = {
            "symbol": "XAUUSDm",
            "bid": 2650.0,
            "ask": 2650.24,
            "spread": 0.24,
            "server_timestamp_utc": "2026-11-12T09:00:00Z",
            "collection_timestamp_utc": "2026-11-12T09:00:01Z",
            "validation_status": "OK",
        }
        q.update(kw)
        return q

    def test_ok_quote(self):
        v = validate_quote_record(self._base())
        self.assertTrue(v["usable"])
        self.assertAlmostEqual(v["spread_price"], 0.24)
        self.assertAlmostEqual(v["spread_points"], 240.0)

    def test_crossed_market_rejected(self):
        v = validate_quote_record(self._base(bid=2651.0, ask=2650.0))
        self.assertFalse(v["usable"])
        self.assertIn("crossed_market", v["quality_flags"])

    def test_stale_quote_rejected(self):
        v = validate_quote_record(
            self._base(
                server_timestamp_utc="2026-11-12T08:00:00Z",
                collection_timestamp_utc="2026-11-12T09:00:00Z",
            )
        )
        self.assertFalse(v["usable"])
        self.assertIn("stale_quote", v["quality_flags"])

    def test_superseded_symbol_rejected(self):
        v = validate_quote_record(self._base(symbol="XAUUSD"))
        self.assertFalse(v["usable"])


class TestSpreadAnalysis(unittest.TestCase):
    def test_live_spread_runs(self):
        out = analyze_live_spreads()
        self.assertIn("n_usable_quotes", out)
        self.assertIn("distribution_price_units", out)
        self.assertFalse(out["high_volatility_periods"]["classified"])
        dist = out["distribution_price_units"]
        if out["n_usable_quotes"] > 0:
            self.assertIsNotNone(dist["median"])
            self.assertIsNotNone(dist["p90"])


class TestCostModel(unittest.TestCase):
    def test_versioned_and_unknown_not_zero(self):
        cm = build_cost_model(
            observed_spread_price_median=0.24,
            observed_spread_points_median=240.0,
            spread_n=100,
            commission_status=UNKNOWN,
            commission_value=UNKNOWN,
            swap_status="CONFLICTED",
        )
        self.assertEqual(cm["cost_model_version"], COST_MODEL_VERSION)
        self.assertEqual(cm["NET_PROFITABILITY"], "NOT_ESTABLISHED")
        self.assertFalse(cm["production_approved"])
        self.assertFalse(cm["unknown_components_treated_as_zero"])
        for c in cm["components"]:
            self.assertFalse(c["silently_zeroed"])
            if c["component"] == "commission":
                self.assertEqual(c["value"], UNKNOWN)
                self.assertNotEqual(c["value"], 0)

    def test_conflicted_swap_preserved(self):
        cm = build_cost_model(
            observed_spread_price_median=0.24,
            observed_spread_points_median=240.0,
            spread_n=50,
            swap_status="CONFLICTED",
            swap_value={"a": -488.7, "b": -644.8},
        )
        swap = next(c for c in cm["components"] if c["component"] == "swap")
        self.assertEqual(swap["status"], "CONFLICTED")
        self.assertIsInstance(swap["value"], dict)

    def test_gross_vs_net_accounting(self):
        cm = build_cost_model(
            observed_spread_price_median=0.24,
            observed_spread_points_median=240.0,
            spread_n=50,
        )
        adj = apply_costs_to_trade_r(
            gross_r=2.0,
            risk_price=1.0,
            spread_price=0.24,
            commission_r=None,
            swap_r=None,
            slippage_r=None,
            cost_model=cm,
        )
        self.assertEqual(adj["gross_r"], 2.0)
        self.assertAlmostEqual(adj["known_cost_adjusted_r"], 1.76)
        self.assertIsNone(adj["net_r"])
        self.assertEqual(adj["NET_PROFITABILITY"], "NOT_ESTABLISHED")


class TestSensitivity(unittest.TestCase):
    def test_break_even_and_unknown_commission(self):
        out = evaluate_trade_cost_sensitivity(
            entry=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            holding_bars=10,
            direction="BUY",
            observed_spread_price=0.24,
            commission_r=None,
            nights=0,
        )
        self.assertAlmostEqual(out["gross_reward_risk"], 2.0)
        self.assertAlmostEqual(out["break_even_win_rate_gross"], 1.0 / 3.0)
        self.assertEqual(out["inputs"]["commission_r"], UNKNOWN)
        self.assertIn("retune_H70", out["forbids"])

    def test_timezone_session_buckets_exist_in_spread(self):
        # Session classification exercised via spread analysis buckets
        out = analyze_live_spreads()
        self.assertIsInstance(out.get("by_session_bucket"), dict)


class TestEvidenceAndCollector(unittest.TestCase):
    def test_qualification_no_backfill_mix(self):
        q = build_live_evidence_qualification()
        self.assertTrue(q["backfill_never_combined_with_live_for_qualification"])
        self.assertFalse(q["phase58_holdout_accessed"])
        self.assertLess(q["n_complete_independent_live_dates"], 20)

    def test_collector_health_and_single_instance(self):
        rel = inspect_collector_reliability()
        self.assertIn(rel["health"]["service_status"], ("RUNNING", "STOPPED", "UNKNOWN", None, "ERROR"))
        self.assertFalse(rel["windows_autostart"]["reboot_recovery_claimed"])

    def test_autostart_script_no_secrets(self):
        path = write_autostart_script()
        text = path.read_text(encoding="utf-8")
        for bad in ("PASSWORD=", "investor_password", "api_secret", "login_password"):
            self.assertNotIn(bad, text)
        self.assertIn("phase67.cli", text)
        self.assertIn("UNTESTED", text.upper())
        self.assertTrue(path.is_file())


class TestC07AndSafety(unittest.TestCase):
    def test_c07_not_implemented(self):
        r = build_c07_a_readiness()
        self.assertFalse(r["strategy_implemented"])
        self.assertFalse(r["screened_on_consumed_archives"])
        self.assertFalse(r["h70_revived"])
        self.assertGreaterEqual(len(r["missing_from_original_discovery_rationale"]), 3)

    def test_safety_invariants(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertEqual(ORDER_SEND, "PROHIBITED")

    def test_no_holdout_access_in_package(self):
        root = PROJECT_ROOT / "src" / "signal_bot" / "execution_economics"
        for p in root.glob("*.py"):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("holdout_results.json", text)


if __name__ == "__main__":
    unittest.main()
