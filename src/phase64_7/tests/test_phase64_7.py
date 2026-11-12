"""Unit tests for Phase 64.7."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_7.adversarial import run_adversarial_tests
from phase64_7.api_security_review import build_api_security_review
from phase64_7.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    DEMO_COLLECTION,
    EXPECTED_NULL_POLICY,
    LIVE_TRADING,
    RECIPE_ID,
    UNAPPROVED,
)
from phase64_7.execution_recon_design import audit_recon_design
from phase64_7.integrity import audit_integrity
from phase64_7.live_probe import run_live_probe, sanitize_account


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_7_live_mt5_readonly_probe_api_security_review_v1")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)

    def test_allowlist_phase64_8_ro_expansion(self):
        """Phase64.7 left allowlist unchanged; Phase64.8 approved four RO APIs. Mutation stays prohibited."""
        self.assertIn("symbol_info", PERMITTED_MT5_API)
        self.assertIn("positions_get", PERMITTED_MT5_API)
        self.assertIn("history_deals_get", PERMITTED_MT5_API)
        self.assertIn("order_send", PROHIBITED_MT5_API)

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_posture(self):
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(DEMO_COLLECTION, "READ_ONLY")
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertIs(BROKER_EXECUTION_READY, False)


class TestCore(unittest.TestCase):
    def test_sanitize_no_full_login(self):
        s = sanitize_account({"login": 474906834, "server": "Exness-MT5Trial15", "account_identity_fingerprint": "x"})
        self.assertEqual(s["login_last4"], "6834")
        self.assertNotIn("login", s)

    def test_api_security(self):
        self.assertTrue(build_api_security_review()["pass"])

    def test_recon_design(self):
        self.assertTrue(audit_recon_design()["pass"])

    def test_live_probe_or_blocked(self):
        """Live terminal may or may not be up in CI; both OK/BLOCKED are valid evidence."""
        p = run_live_probe()
        self.assertIn(p["status"], ("LIVE_PROBE_OK", "PROBE_BLOCKED"))
        if p["status"] == "LIVE_PROBE_OK":
            self.assertEqual(p["raw"]["evidence_type"], "LIVE_MT5_API")
            self.assertFalse(p["sanitized"]["fixture_used"])
            self.assertFalse(p["sanitized"]["order_send_invoked"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])

    def test_risk_still_unapproved(self):
        self.assertEqual(UNAPPROVED, "UNAPPROVED")


if __name__ == "__main__":
    unittest.main()
