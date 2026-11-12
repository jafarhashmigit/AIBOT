"""Phase 61 tests — Exness evidence honesty, unknown refusal, integrity."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from phase54.decision import NullPolicy
from phase61.adapters import null_policy_ok, phase58_holdout
from phase61.commission import ExnessCommissionModel, calibrate_commission, PUBLISHED_XAUUSD_REFERENCE
from phase61.constants import EXPECTED_NULL_POLICY, PHASE60_REPORTS, PROJECT_ROOT, RECIPE_ID
from phase61.cost_ledger import audit_ledger_examples, build_trade_ledger
from phase61.evidence_registry import build_official_evidence_registry
from phase61.execution_evidence import ExecutionEvidenceCollector, ExnessEvidenceAdapter, evidence_schema
from phase61.identity import build_account_identity
from phase61.integrity import audit_integrity
from phase61.latency import analyze_latency, ms_between
from phase61.slippage import build_slippage_study, signed_entry_slippage, signed_exit_slippage
from phase61.sufficiency import assess_sufficiency
from phase61.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_null_policy(self):
        self.assertTrue(null_policy_ok())
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_holdout(self):
        h = phase58_holdout()
        self.assertEqual(len(h), 10)

    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase61_exness_execution_evidence_calibration_v1")


class TestIdentity(unittest.TestCase):
    def test_account_unknown(self):
        ident = build_account_identity()
        self.assertEqual(ident["account_type"], "UNKNOWN")
        self.assertEqual(ident["broker_symbol"], "UNKNOWN")
        self.assertFalse(ident["account_login_stored"])
        self.assertIn("suffix", ident["suffix_ambiguity_note"].lower())


class TestEvidenceRegistry(unittest.TestCase):
    def test_provenance_fields(self):
        reg = build_official_evidence_registry()
        self.assertGreaterEqual(reg["n_facts"], 8)
        self.assertFalse(reg["active_account_configuration"])
        f0 = reg["facts"][0]
        for k in (
            "claim",
            "source_url",
            "retrieval_timestamp_utc",
            "verification_status",
            "account_specific_confirmation_required",
        ):
            self.assertIn(k, f0)


class TestCommission(unittest.TestCase):
    def test_unknown_refuses(self):
        ident = build_account_identity()
        reg = build_official_evidence_registry()
        cal = calibrate_commission(ident, reg)
        self.assertEqual(cal["commission_status"], "UNKNOWN")
        self.assertFalse(cal["published_reference_active_in_model"])
        m = ExnessCommissionModel(cal)
        self.assertIsNone(m.commission_for_volume(lots=1.0, sides=2))
        self.assertIsNone(m.commission_adjusted_net_r(gross_r=1.0, risk_amount=100.0, lots=1.0, sides=2))

    def test_verified_raw_spread_units(self):
        ident = {
            "account_type": "Raw Spread",
            "broker_symbol": "XAUUSD",
            "verification_status": "VERIFIED",
            "sha256": "x",
        }
        cal = calibrate_commission(ident, {"sha256": "y"})
        self.assertEqual(cal["commission_status"], "VERIFIED")
        m = ExnessCommissionModel(cal)
        # 1 lot round-turn at open = 3.5 * 2
        ee = m.entry_and_exit_commission(entry_lots=1.0)
        self.assertEqual(ee["total"], 7.0)
        self.assertEqual(ee["exit"], 0.0)
        partial = m.partial_close_allocation(total_round_turn_commission=7.0, closed_lots=0.5, original_lots=1.0)
        self.assertEqual(partial, 3.5)
        multi = m.multiple_fills_commission(fill_lots=[0.01, 0.02], sides_per_fill=2)
        self.assertAlmostEqual(multi, 3.5 * 0.03 * 2)

    def test_commission_free_pro(self):
        ident = {
            "account_type": "Pro",
            "broker_symbol": "XAUUSD",
            "verification_status": "VERIFIED",
            "sha256": "x",
        }
        m = ExnessCommissionModel(calibrate_commission(ident, {"sha256": "y"}))
        self.assertEqual(m.commission_for_volume(lots=1.0, sides=2), 0.0)

    def test_fx_missing_refuses(self):
        ident = {
            "account_type": "Raw Spread",
            "broker_symbol": "XAUUSD",
            "verification_status": "VERIFIED",
            "sha256": "x",
        }
        m = ExnessCommissionModel(calibrate_commission(ident, {"sha256": "y"}))
        self.assertIsNone(m.commission_for_volume(lots=1.0, sides=1, account_currency="EUR", fx_to_account=None))

    def test_published_reference_exists_but_inactive(self):
        self.assertIn("Raw Spread", PUBLISHED_XAUUSD_REFERENCE)
        self.assertEqual(PUBLISHED_XAUUSD_REFERENCE["Raw Spread"]["usd_per_lot_per_side"], 3.5)


class TestExecutionEvidence(unittest.TestCase):
    def test_schema_categories(self):
        s = evidence_schema()
        self.assertIn("EXNESS_DEMO_EXECUTION", s["categories"])
        self.assertTrue(s["never_cross_prove"])

    def test_proxy_cannot_set_actual_fill(self):
        with tempfile.TemporaryDirectory() as td:
            c = ExecutionEvidenceCollector(root=Path(td))
            with self.assertRaises(ValueError):
                c.record(
                    {
                        "decision_id": "d1",
                        "side": "BUY",
                        "evidence_category": "HISTORICAL_QUOTE_PROXY",
                        "source_provenance": "test",
                        "actual_broker_fill_price": 1.0,
                    }
                )

    def test_live_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            c = ExecutionEvidenceCollector(root=Path(td))
            with self.assertRaises(ValueError):
                c.record(
                    {
                        "decision_id": "d1",
                        "side": "BUY",
                        "evidence_category": "EXNESS_LIVE_EXECUTION",
                        "source_provenance": "test",
                    }
                )

    def test_capability_no_live(self):
        cap = ExnessEvidenceAdapter().capability()
        self.assertFalse(cap["live_mt5_connection"])
        self.assertFalse(cap["live_order_submission"])
        self.assertTrue(cap["exness_live_blocked"])


class TestSlippage(unittest.TestCase):
    def test_bid_ask_semantics(self):
        b = signed_entry_slippage(side="BUY", decision_bid=100.0, decision_ask=100.2, fill=100.4)
        self.assertEqual(b["benchmark"], "decision_ASK")
        self.assertAlmostEqual(b["adverse"], 0.2)
        s = signed_entry_slippage(side="SELL", decision_bid=100.0, decision_ask=100.2, fill=99.7)
        self.assertEqual(s["benchmark"], "decision_BID")
        self.assertAlmostEqual(s["adverse"], 0.3)
        ex = signed_exit_slippage(position_side="BUY", decision_bid=100.0, decision_ask=100.2, fill=99.5)
        self.assertGreater(ex["adverse"], 0)

    def test_actual_unknown_without_fills(self):
        study = build_slippage_study([])
        self.assertEqual(study["actual_slippage_status"], "UNKNOWN")
        self.assertFalse(study["live_cost_calibration_from_proxy_alone"])


class TestLatency(unittest.TestCase):
    def test_ms_between(self):
        self.assertEqual(ms_between("2026-01-01 12:00:00", "2026-01-01 12:00:01"), 1000.0)
        self.assertIsNone(ms_between(None, "2026-01-01 12:00:00"))

    def test_unavailable_without_ts(self):
        r = analyze_latency([{"evidence_category": "SIMULATED_PAPER"}])
        self.assertEqual(r["broker_latency_status"], "UNKNOWN")


class TestLedger(unittest.TestCase):
    def test_unknown_refuses_total(self):
        audit = audit_ledger_examples()
        self.assertTrue(audit["pass_unknown_refuses_total"])
        self.assertTrue(audit["pass_complete_has_total"])

    def test_no_double_count_spread(self):
        led = build_trade_ledger(
            gross_price_move=1.0,
            spread_cost=0.2,
            spread_already_in_fill=True,
            commission=0.0,
            commission_status="VERIFIED",
            slippage=0.0,
            slippage_status="MEASURED",
            swap=0.0,
            swap_status="VERIFIED_INTRADAY_ZERO",
        )
        self.assertTrue(led["double_count_spread_prevented"])
        spread = next(c for c in led["components"] if c["name"] == "SPREAD_COST")
        self.assertEqual(spread["status"], "EMBEDDED_IN_FILL_NOT_ADDED_AGAIN")


class TestSufficiency(unittest.TestCase):
    def test_preregistered_fail_small_sample(self):
        a = assess_sufficiency(
            n_independent_decisions=10,
            n_actual_fills=10,
            n_trading_days=2,
            sessions_represented=1,
            missing_record_rate=0.5,
            account_consistent=False,
            volume_consistent=False,
        )
        self.assertFalse(a["sufficient_for_account_specific_cost_model"])
        self.assertFalse(a["small_demo_sample_establishes_live_economics"])
        self.assertTrue(a["thresholds_chosen_before_outcome_analysis"])


class TestIntegrity(unittest.TestCase):
    def test_holdout_and_phase60(self):
        a = audit_integrity()
        self.assertTrue(a["phase58_holdout_sealed"])
        self.assertFalse(a["stores_merged"])
        self.assertFalse(a["new_trading_model_introduced"])
        self.assertTrue((PHASE60_REPORTS / "PHASE60_FINAL_REPORT.md").is_file())


class TestVerdict(unittest.TestCase):
    def test_partial_when_unknown(self):
        v, _ = choose_verdict(
            identity={"account_type": "UNKNOWN"},
            commission={"commission_status": "UNKNOWN"},
            slippage={"actual_slippage_status": "UNKNOWN"},
            sufficiency={"sufficient_for_account_specific_cost_model": False},
            integrity={"checks_pass": True},
            capability={"can_collect_actual_demo_fills_without_live_orders": False},
            holdout_sealed=True,
            null_ok=True,
            tests_ok=True,
        )
        self.assertEqual(v, "EXNESS_EXECUTION_EVIDENCE_PARTIAL")

    def test_blocked_tests(self):
        v, _ = choose_verdict(
            identity={"account_type": "Pro", "verification_status": "VERIFIED"},
            commission={"commission_status": "VERIFIED"},
            slippage={"actual_slippage_status": "MEASURED"},
            sufficiency={"sufficient_for_account_specific_cost_model": True},
            integrity={"checks_pass": True},
            capability={"can_collect_actual_demo_fills_without_live_orders": True},
            holdout_sealed=True,
            null_ok=True,
            tests_ok=False,
        )
        self.assertEqual(v, "EXNESS_EXECUTION_EVIDENCE_BLOCKED")


class TestImmutability(unittest.TestCase):
    def test_phase61_paths(self):
        self.assertTrue((PROJECT_ROOT / "src" / "phase61").is_dir())
        self.assertTrue((PHASE60_REPORTS / "PHASE60_FINAL_REPORT.md").is_file())


if __name__ == "__main__":
    unittest.main()
