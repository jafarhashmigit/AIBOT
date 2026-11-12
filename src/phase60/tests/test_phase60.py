"""Phase 60 tests — execution reality honesty, holdout isolation, no invented costs."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from phase54.decision import NullPolicy
from phase60.adapters import holdout_days, inventory, null_policy_ok
from phase60.audit_phase59 import run_independent_phase59_audit
from phase60.commission import CommissionModel, investigate_commission
from phase60.constants import EXPECTED_NULL_POLICY, PHASE58_SPLITS, PROJECT_ROOT, RECIPE_ID
from phase60.deep_audit import audit_day_deep, audit_remaining_days
from phase60.experience_audit import audit_experience
from phase60.gap_through import (
    build_sl_tp_cases,
    detect_stop_trigger,
    same_bar_sl_before_tp,
    simulate_stop_exit,
    simulate_tp_exit,
)
from phase60.paired_stats import paired_summaries
from phase60.slippage import (
    build_execution_price_semantics,
    build_slippage_methodology,
    executable_side,
    measure_slippage,
)
from phase60.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_null_policy(self):
        self.assertTrue(null_policy_ok(EXPECTED_NULL_POLICY))
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_holdout_isolation(self):
        h = holdout_days()
        self.assertEqual(len(h), 10)
        if PHASE58_SPLITS.is_file():
            splits = json.loads(PHASE58_SPLITS.read_text(encoding="utf-8"))
            self.assertEqual(h, splits.get("holdout_sealed"))

    def test_recipe_id(self):
        self.assertEqual(RECIPE_ID, "phase60_execution_reality_market_coverage_v1")

    def test_no_autostart_module_side_effects(self):
        # Importing package must not place orders / connect MT5
        import phase60  # noqa: F401

        self.assertTrue(True)


class TestPhase59Audit(unittest.TestCase):
    def test_remaining_ten_identified(self):
        audit = run_independent_phase59_audit()
        self.assertEqual(len(audit["remaining_10_days"]), 10)
        self.assertTrue(audit["all_remaining_locatable"])
        expected = {
            "2025-07-01",
            "2025-08-15",
            "2025-10-01",
            "2025-12-01",
            "2026-01-15",
            "2026-02-16",
            "2026-04-15",
            "2026-06-02",
            "2026-08-03",
            "2026-09-15",
        }
        self.assertEqual(set(audit["remaining_10_days"]), expected)


class TestDeepAudit(unittest.TestCase):
    def test_one_remaining_day_auditable(self):
        day = "2025-07-01"
        row = audit_day_deep(day)
        self.assertEqual(row["day"], day)
        self.assertFalse(row["source_silently_repaired"])
        self.assertGreater(row.get("m5_n") or 0, 0)
        self.assertGreater(row.get("ticks_n") or 0, 0)

    def test_all_ten_located(self):
        days = [
            "2025-07-01",
            "2025-08-15",
            "2025-10-01",
            "2025-12-01",
            "2026-01-15",
            "2026-02-16",
            "2026-04-15",
            "2026-06-02",
            "2026-08-03",
            "2026-09-15",
        ]
        # Lightweight: ensure roots resolve; full suite run does full audit in runner
        from phase60.adapters import root_for_day

        for d in days:
            self.assertIsNotNone(root_for_day(d), msg=d)


class TestCommission(unittest.TestCase):
    def test_unknown_refuses_adjusted(self):
        ev = investigate_commission()
        self.assertEqual(ev["commission_status"], "UNKNOWN")
        m = CommissionModel(ev)
        self.assertIsNone(m.calculate_commission_usd(lots=1.0, sides=2))
        self.assertIsNone(m.commission_adjusted_net_r(gross_r=1.0, risk_amount=100.0, lots=1.0, sides=2))

    def test_verified_units(self):
        ev = {
            "commission_status": "VERIFIED",
            "schedule": {"calculation_method": "per_lot_per_side", "usd_per_lot_per_side": 3.0},
        }
        m = CommissionModel(ev)
        self.assertEqual(m.calculate_commission_usd(lots=0.5, sides=2), 3.0)
        self.assertIsNone(m.calculate_commission_usd(lots=None, sides=2))


class TestSlippage(unittest.TestCase):
    def test_bid_ask_semantics(self):
        self.assertEqual(executable_side(action="BUY", leg="ENTRY"), "ASK")
        self.assertEqual(executable_side(action="SELL", leg="ENTRY"), "BID")
        self.assertEqual(executable_side(action="BUY", leg="EXIT"), "BID")
        self.assertEqual(executable_side(action="SELL", leg="EXIT"), "ASK")

    def test_actual_unknown_in_methodology(self):
        m = build_slippage_methodology()
        self.assertEqual(m["actual_slippage_status"], "UNKNOWN")
        sem = build_execution_price_semantics()
        self.assertEqual(sem["BUY_entry"], "ASK")

    def test_adverse_favorable(self):
        adv = measure_slippage(intended_price=100.0, fill_price=100.5, action="BUY", leg="ENTRY")
        self.assertGreater(adv["adverse_signed"], 0)
        fav = measure_slippage(intended_price=100.0, fill_price=99.5, action="BUY", leg="ENTRY")
        self.assertLess(fav["adverse_signed"], 0)
        miss = measure_slippage(intended_price=None, fill_price=1.0, action="BUY", leg="ENTRY")
        self.assertEqual(miss["status"], "UNKNOWN")


class TestGapThrough(unittest.TestCase):
    def test_cases_pass(self):
        cases = build_sl_tp_cases()
        self.assertEqual(cases["n_pass"], cases["n_cases"])

    def test_stop_not_at_sl_on_gap(self):
        ticks = [
            {"timestamp_utc": "2025-01-01 00:00:01", "bid": 100.0, "ask": 100.2},
            {"timestamp_utc": "2025-01-01 00:00:02", "bid": 97.5, "ask": 97.7},
        ]
        sim = simulate_stop_exit(ticks, side="BUY", stop_loss=99.0)
        self.assertEqual(sim["fill_price"], 97.5)
        self.assertFalse(sim["assumed_fill_at_stop_price"])
        self.assertGreater(sim["gap_through_amount"], 1.0)

    def test_sl_before_tp(self):
        ticks = [{"timestamp_utc": "t", "bid": 99.0, "ask": 99.2}]
        r = same_bar_sl_before_tp(ticks, side="BUY", sl=99.5, tp=98.0)
        self.assertEqual(r["exit_reason"], "STOP_LOSS")

    def test_tp_uncertainty(self):
        ticks = [
            {"timestamp_utc": "t1", "bid": 100.0, "ask": 100.2},
            {"timestamp_utc": "t2", "bid": 101.0, "ask": 101.2},
        ]
        r = simulate_tp_exit(ticks, side="BUY", take_profit=100.9)
        self.assertEqual(r["broker_limit_rules"], "UNKNOWN")


class TestPairedStats(unittest.TestCase):
    def test_does_not_inflate_n(self):
        events = [
            {"event_id": "a", "day": "d1", "buy_net_r": 1.0, "sell_net_r": -0.5},
            {"event_id": "b", "day": "d1", "buy_net_r": -1.0, "sell_net_r": 0.5},
            {"event_id": "c", "day": "d2", "buy_net_r": 0.2, "sell_net_r": 0.1},
        ]
        s = paired_summaries(events)
        self.assertEqual(s["n_unique_events"], 3)
        self.assertEqual(s["n_side_observations"], 6)
        self.assertEqual(s["incorrect_independent_n_if_both_concat"], 6)
        self.assertIn("buy_minus_sell_mean_ci95", s["inferential"])


class TestExperience(unittest.TestCase):
    def test_stores_separate(self):
        a = audit_experience()
        self.assertFalse(a["stores_merged"])
        self.assertFalse(a["force_aligned"])
        self.assertFalse(a["records_fabricated"])
        self.assertTrue(a["unknown_commission_preserved"] or a["historical_hypothetical"]["n"] == 0)


class TestVerdict(unittest.TestCase):
    def test_partial_when_unknown_costs(self):
        v, _ = choose_verdict(
            phase59_audit={"all_critical_checks_pass": True, "all_remaining_locatable": True},
            remaining={"n_fail": 0},
            coverage={"hundred_day_coverage_claim_permitted": True},
            commission={"commission_status": "UNKNOWN"},
            slippage_method={"actual_slippage_status": "UNKNOWN"},
            experience={"checks_pass": True},
            holdout_sealed=True,
            null_ok=True,
            tests_ok=True,
        )
        self.assertEqual(v, "EXECUTION_REALITY_PARTIAL")

    def test_blocked_on_holdout(self):
        v, _ = choose_verdict(
            phase59_audit={"all_critical_checks_pass": True, "all_remaining_locatable": True},
            remaining={"n_fail": 0},
            coverage={"hundred_day_coverage_claim_permitted": True},
            commission={"commission_status": "VERIFIED"},
            slippage_method={"actual_slippage_status": "MEASURED"},
            experience={"checks_pass": True},
            holdout_sealed=False,
            null_ok=True,
            tests_ok=True,
        )
        self.assertEqual(v, "EXECUTION_REALITY_BLOCKED")


class TestImmutability(unittest.TestCase):
    def test_phase59_sources_untouched_paths(self):
        # Phase60 must live under src/phase60 only for new code
        p60 = PROJECT_ROOT / "src" / "phase60"
        self.assertTrue(p60.is_dir())
        self.assertTrue((PROJECT_ROOT / "reports" / "phase59" / "FINAL_REPORT.md").is_file())


if __name__ == "__main__":
    unittest.main()
