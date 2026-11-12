"""Phase 63 tests — XAUUSDm active, XAUUSD superseded, no leakage."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase62.store import ExecutionStore
from phase63.constants import EXPECTED_NULL_POLICY, META_DIR, RECIPE_ID, VERIFICATION_STATUS
from phase63.economics import build_economics_ledger
from phase63.importers_adversarial import run_adversarial_import_tests
from phase63.integrity import audit_integrity, phase58_holdout
from phase63.metadata import (
    ACTIVE_SYMBOL,
    ACTIVE_XAUUSDM_SPEC,
    SUPERSEDED_SYMBOL,
    SUPERSEDED_XAUUSD_SPEC,
    SUPERSESSION_REASON,
    assert_no_xauusd_leakage,
    get_active_profile,
    get_active_symbol,
    register_metadata,
)
from phase63.sufficiency import assess_sufficiency
from phase63.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_null_recipe(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)
        self.assertEqual(RECIPE_ID, "phase63_exness_demo_execution_evidence_integration_v1")

    def test_holdout(self):
        self.assertEqual(len(phase58_holdout()), 10)

    def test_no_order_send_allowlist(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        # Phase64.8 approved history_deals_get RO; order_send remains prohibited.
        from phase12.mt5_allowlist import PERMITTED_MT5_API

        self.assertIn("history_deals_get", PERMITTED_MT5_API)


class TestBrokerMetadataCorrection(unittest.TestCase):
    def test_xauusdm_is_active_symbol(self):
        meta = register_metadata(observation_timestamp_utc="2026-11-11T19:00:00Z")
        self.assertEqual(meta["values"]["symbol"], "XAUUSDm")
        self.assertEqual(meta["profile_status"], "ACTIVE")
        self.assertEqual(get_active_symbol(), ACTIVE_SYMBOL)
        self.assertEqual(ACTIVE_SYMBOL, "XAUUSDm")

    def test_previous_xauusd_superseded(self):
        register_metadata(observation_timestamp_utc="2026-11-11T19:00:01Z")
        path = META_DIR / "exness_mt5_spec_SUPERSEDED_XAUUSD.json"
        self.assertTrue(path.is_file())
        old = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(old["profile_status"], "SUPERSEDED")
        self.assertEqual(old["supersession_reason"], SUPERSESSION_REASON)
        self.assertEqual(old["values"]["symbol"], SUPERSEDED_SYMBOL)
        self.assertTrue(old["do_not_use_for_active_selection"])
        self.assertFalse(old.get("active", False))

    def test_old_tick_value_cannot_leak(self):
        meta = register_metadata(observation_timestamp_utc="2026-11-11T19:00:02Z")
        self.assertEqual(meta["values"]["tick_value"], "UNKNOWN")
        self.assertNotEqual(meta["values"]["tick_value"], SUPERSEDED_XAUUSD_SPEC["tick_value"])
        self.assertEqual(SUPERSEDED_XAUUSD_SPEC["tick_value"], 0.10)
        self.assertEqual(assert_no_xauusd_leakage(meta), [])

    def test_old_cfd_leverage_cannot_leak(self):
        meta = register_metadata(observation_timestamp_utc="2026-11-11T19:00:03Z")
        self.assertEqual(meta["values"]["calculation_mode"], "FOREX")
        self.assertEqual(SUPERSEDED_XAUUSD_SPEC["calculation_mode"], "CFD_LEVERAGE")
        self.assertNotEqual(meta["values"]["calculation_mode"], "CFD_LEVERAGE")

    def test_margin_xau_profit_usd(self):
        meta = register_metadata(observation_timestamp_utc="2026-11-11T19:00:04Z")
        self.assertEqual(meta["values"]["margin_currency"], "XAU")
        self.assertEqual(meta["values"]["profit_currency"], "USD")

    def test_missing_specs_remain_unknown(self):
        meta = register_metadata(observation_timestamp_utc="2026-11-11T19:00:05Z")
        v = meta["values"]
        for field in (
            "tick_size",
            "tick_value",
            "tick_value_profit",
            "tick_value_loss",
            "account_currency",
            "account_leverage",
        ):
            self.assertEqual(v[field], "UNKNOWN", msg=field)
        self.assertIsNone(v["margin_rates"]["market_sell_usd_per_lot"])
        self.assertIn("tick_value", meta["missing_specifications"])

    def test_partial_sessions_incomplete(self):
        meta = register_metadata(observation_timestamp_utc="2026-11-11T19:00:06Z")
        sess = meta["values"]["trading_sessions"]
        self.assertEqual(sess["completeness"], "PARTIAL")
        self.assertFalse(sess["missing_closing_times_invented"])
        self.assertEqual(sess["monday_to_thursday"]["segment_2_end"], "TRUNCATED_UNKNOWN")
        self.assertEqual(sess["saturday"], "CLOSED")

    def test_selection_no_fallback(self):
        register_metadata(observation_timestamp_utc="2026-11-11T19:00:07Z")
        sel = json.loads((META_DIR / "active_broker_selection.json").read_text(encoding="utf-8"))
        self.assertEqual(sel["active_symbol"], "XAUUSDm")
        self.assertFalse(sel["fallback_to_superseded_allowed"])
        active = get_active_profile()
        self.assertEqual(active["values"]["symbol"], "XAUUSDm")

    def test_intake_uses_xauusdm_unknown_ticks(self):
        register_metadata(observation_timestamp_utc="2026-11-11T19:00:08Z")
        intake = json.loads((META_DIR / "phase62_compatible_intake.json").read_text(encoding="utf-8"))
        self.assertEqual(intake["exact_broker_symbol"], "XAUUSDm")
        self.assertEqual(intake["tick_value"], "UNKNOWN")
        self.assertEqual(intake["tick_size"], "UNKNOWN")
        self.assertNotEqual(intake["tick_value"], 0.10)
        self.assertNotIn("password", intake)

    def test_active_spec_constants(self):
        self.assertEqual(ACTIVE_XAUUSDM_SPEC["symbol"], "XAUUSDm")
        self.assertEqual(ACTIVE_XAUUSDM_SPEC["execution_mode"], "MARKET")
        self.assertEqual(ACTIVE_XAUUSDM_SPEC["digits"], 3)


class TestEconomics(unittest.TestCase):
    def test_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            store.ingest_normalized(
                {
                    "broker": "Exness",
                    "environment": "DEMO",
                    "deal_id": "E1",
                    "record_kind": "DEAL",
                    "side": "BUY",
                    "symbol": "XAUUSDm",
                    "volume": 0.01,
                    "actual_fill_price": 2600.0,
                    "fill_timestamp_utc": "2026-01-01 12:00:00",
                    "commission": None,
                    "source_provenance": "t",
                    "synthetic": False,
                }
            )
            led = build_economics_ledger(
                store, {"values": {"symbol": "XAUUSDm", "tick_value": "UNKNOWN", "calculation_mode": "FOREX"}}
            )
            self.assertFalse(led["missing_treated_as_zero"])
            self.assertEqual(led["sample_rows"][0]["commission"], "UNKNOWN")


class TestSufficiency(unittest.TestCase):
    def test_not_lowered_and_insufficient(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            s = assess_sufficiency(store)
            self.assertFalse(s["thresholds_lowered"])
            self.assertFalse(s["sufficient"])


class TestAdversarial(unittest.TestCase):
    def test_adversarial_suite(self):
        a = run_adversarial_import_tests()
        self.assertTrue(a["pass"])


class TestIntegrityVerdict(unittest.TestCase):
    def test_integrity_historical_shadow_unchanged_flags(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            a = audit_integrity(store)
            self.assertTrue(a["phase58_holdout_sealed"])
            self.assertFalse(a["stores_merged"])
            self.assertFalse(a["phase0_62_source_modified"])
            self.assertFalse(a["allowlist_expanded"])

    def test_awaiting_export_verdict(self):
        v, _ = choose_verdict(
            metadata={"verification_status": VERIFICATION_STATUS},
            import_result={"status": "AWAITING_GENUINE_DEMO_EXPORT", "fabricated_evidence": False},
            sufficiency={"sufficient": False, "observed": {"n_actual_fills": 0}},
            integrity={"checks_pass": True},
            tests_ok=True,
            null_ok=True,
        )
        self.assertEqual(v, "AWAITING_GENUINE_DEMO_EXPORT")


if __name__ == "__main__":
    unittest.main()
