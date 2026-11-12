"""Phase 62 tests — intake, import, store recovery, security."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase62.adapters import mt5_api_capability, null_policy_ok, phase58_holdout
from phase62.capability import build_capability_matrix, discover_integrations, platform_integration_decision
from phase62.constants import EXPECTED_NULL_POLICY, FORBIDDEN_INTAKE_KEYS, PHASE61_REPORTS, RECIPE_ID
from phase62.cost_evidence import demo_cost_evidence_status
from phase62.domains import audit_domains
from phase62.importers import import_csv, import_json_records, write_synthetic_fixtures
from phase62.intake import build_identity_status, intake_schema, load_intake_file
from phase62.integrity import phase_integrity_audit
from phase62.schema import execution_record_schema
from phase62.store import ExecutionStore, recovery_audit
from phase62.sufficiency import accumulate
from phase62.verdict import choose_verdict


class TestSafety(unittest.TestCase):
    def test_null_and_recipe(self):
        self.assertTrue(null_policy_ok())
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)
        self.assertEqual(RECIPE_ID, "phase62_exness_demo_execution_collector_v1")

    def test_holdout(self):
        self.assertEqual(len(phase58_holdout()), 10)

    def test_order_send_prohibited(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        # Phase64.8 approved history_deals_get as RO; Phase62 still does not activate native pull.
        self.assertIn("history_deals_get", PERMITTED_MT5_API)
        cap = mt5_api_capability()
        self.assertTrue(cap["history_deals_get_permitted"])
        self.assertTrue(cap["order_send_prohibited"])


class TestIntake(unittest.TestCase):
    def test_schema_forbids_credentials(self):
        s = intake_schema()
        self.assertIn("password", s["forbidden_keys"])

    def test_missing_intake_unknown(self):
        ident = build_identity_status(intake=None)
        self.assertEqual(ident["account_type"], "UNKNOWN")
        self.assertFalse(ident["core_identity_verified"])
        self.assertFalse(ident["suffix_inference_used"])
        self.assertFalse(ident["credentials_persisted"])

    def test_reject_password_key(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "account_metadata.json"
            p.write_text(json.dumps({"account_type": "Pro", "password": "x"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_intake_file(p)

    def test_suffix_not_verified_account_type(self):
        raw = {
            "broker": "Exness",
            "environment": "DEMO",
            "account_type": "Pro",
            "account_type__status": "VERIFIED",
            "verified_via_suffix_only": True,
            "account_currency": "USD",
            "platform": "MT5",
            "exact_broker_symbol": "XAUUSD",
            "contract_size": 100,
            "tick_size": 0.01,
            "tick_value": "UNKNOWN",
            "volume_minimum": 0.01,
            "volume_step": 0.01,
            "execution_mode": "UNKNOWN",
            "applicable_commission_schedule": "UNKNOWN",
            "swap_configuration": "UNKNOWN",
            "verification_source": "suffix",
            "verification_timestamp_utc": "2026-01-01T00:00:00Z",
        }
        ident = build_identity_status(intake=raw)
        self.assertEqual(ident["fields"]["account_type"]["status"], "USER_PROVIDED_UNVERIFIED")


class TestCapability(unittest.TestCase):
    def test_unknown_platform_csv_path(self):
        ident = build_identity_status(None)
        disc = discover_integrations()
        matrix = build_capability_matrix(ident, disc)
        dec = platform_integration_decision(ident, matrix)
        self.assertIn("CSV", dec["decision"])
        self.assertFalse(dec["native_terminal_connected"])
        self.assertFalse(dec["live_account_access"])


class TestStoreAndImport(unittest.TestCase):
    def test_recovery_audit(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td) / "prod")
            audit = recovery_audit(store)
            self.assertTrue(audit["pass"])

    def test_csv_import_idempotent_and_quarantine(self):
        fixtures = write_synthetic_fixtures()
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            s1 = import_csv(store, Path(fixtures["csv"]))
            s2 = import_csv(store, Path(fixtures["csv"]))
            self.assertGreaterEqual(s1["ingested"], 1)
            self.assertGreaterEqual(s1["quarantined"], 1)  # bad row
            self.assertGreaterEqual(s2["duplicates"], s1["ingested"])
            # commission empty preserved as null
            rows = store.all_normalized()
            self.assertTrue(any(r.get("commission") is None for r in rows))

    def test_synthetic_json_blocked(self):
        fixtures = write_synthetic_fixtures()
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            s = import_json_records(store, Path(fixtures["json"]), allow_synthetic=False)
            self.assertEqual(s["ingested"], 0)
            self.assertGreaterEqual(s["quarantined"], 1)

    def test_conflict_quarantine(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            a = {
                "broker": "Exness",
                "environment": "DEMO",
                "deal_id": "D9",
                "record_kind": "DEAL",
                "actual_fill_price": 1.0,
                "volume": 0.01,
                "side": "BUY",
                "fill_timestamp_utc": "2026-01-01 00:00:00",
                "source_provenance": "t",
                "synthetic": False,
            }
            self.assertEqual(store.ingest_normalized(a)["status"], "INGESTED")
            b = {**a, "actual_fill_price": 2.0}
            self.assertEqual(store.ingest_normalized(b)["status"], "QUARANTINED")

    def test_live_env_quarantine(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            r = store.ingest_normalized(
                {
                    "broker": "Exness",
                    "environment": "LIVE",
                    "deal_id": "L1",
                    "record_kind": "DEAL",
                    "actual_fill_price": 1.0,
                    "source_provenance": "t",
                    "synthetic": False,
                }
            )
            self.assertEqual(r["status"], "QUARANTINED")

    def test_order_not_auto_fill(self):
        schema = execution_record_schema()
        self.assertIn("Do not interpret an order record as a completed fill", schema["rules"])


class TestCostAndSufficiency(unittest.TestCase):
    def test_cost_blocks_adjusted(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            ident = build_identity_status(None)
            st = demo_cost_evidence_status(store, ident)
            self.assertFalse(st["fully_adjusted_performance_allowed"])
            self.assertFalse(st["published_broker_commission_schedule"]["activated"])

    def test_sufficiency_not_lowered(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            acc = accumulate(store, build_identity_status(None))
            self.assertFalse(acc["thresholds_lowered_after_outcomes"])
            self.assertFalse(acc["sufficient_operational_gate"])


class TestDomainsIntegrity(unittest.TestCase):
    def test_domains(self):
        with tempfile.TemporaryDirectory() as td:
            store = ExecutionStore(root=Path(td))
            d = audit_domains(store)
            self.assertFalse(d["stores_merged"])
            self.assertTrue(d["checks_pass"])

    def test_phase_integrity(self):
        a = phase_integrity_audit()
        self.assertTrue(a["phase58_holdout_sealed"])
        self.assertTrue((PHASE61_REPORTS / "PHASE61_FINAL_REPORT.md").is_file())
        self.assertTrue(a["read_only_enforced"])


class TestVerdict(unittest.TestCase):
    def test_partial(self):
        v, _ = choose_verdict(
            identity={"core_identity_verified": False, "intake_file_present": False, "credentials_persisted": False},
            decision={"decision": "PLATFORM_NEUTRAL_CSV_JSON_ONLY", "activated_adapters": ["csv_import"], "native_terminal_connected": False, "live_account_access": False},
            integrity={"checks_pass": True},
            domains={"checks_pass": True},
            recovery={"pass": True},
            holdout_sealed=True,
            null_ok=True,
            tests_ok=True,
            credentials_persisted=False,
            live_access=False,
        )
        self.assertEqual(v, "EXNESS_DEMO_COLLECTION_PARTIAL")

    def test_blocked_credentials(self):
        v, _ = choose_verdict(
            identity={"core_identity_verified": True},
            decision={},
            integrity={"checks_pass": True},
            domains={"checks_pass": True},
            recovery={"pass": True},
            holdout_sealed=True,
            null_ok=True,
            tests_ok=True,
            credentials_persisted=True,
            live_access=False,
        )
        self.assertEqual(v, "EXNESS_DEMO_COLLECTION_BLOCKED")


if __name__ == "__main__":
    unittest.main()
