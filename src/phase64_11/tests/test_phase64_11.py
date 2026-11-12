"""Unit tests for Phase 64.11 — evidence boundary (no order_send)."""

from __future__ import annotations

import unittest

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from phase64_11.adversarial import run_adversarial_tests
from phase64_11.boundary_matrix import build_evidence_boundary_matrix
from phase64_11.commission_boundary import investigate_commission_boundary
from phase64_11.constants import (
    AUTOMATED_ORDERS,
    BOUNDARY_CLASSES,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE,
    EXPECTED_NULL_POLICY,
    LIVE_ACCOUNT,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    RECIPE_ID,
    REQUIRES_GENUINE_ACCOUNT_EVENT,
    STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    SYNTHETIC_TEST,
    UNAPPROVED,
    UNKNOWN,
    USER_REPORTED,
)
from phase64_11.cost_taxonomy import build_cost_taxonomy
from phase64_11.integrity import audit_integrity
from phase64_11.inventory import build_evidence_inventory
from phase64_11.margin_boundary import build_margin_boundary
from phase64_11.risk_policy_evidence import BLOCKED_BY_UNKNOWN, build_risk_policy_evidence
from phase64_11.session_boundary import investigate_session_boundary
from phase64_11.swap_forensic import forensic_swap_reconciliation


class TestSafety(unittest.TestCase):
    def test_recipe(self):
        self.assertEqual(RECIPE_ID, "phase64_11_broker_economics_evidence_boundary_v1")

    def test_order_send(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")

    def test_no_auth(self):
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)
        self.assertEqual(LIVE_TRADING, "NOT_AUTHORIZED")
        self.assertEqual(AUTOMATED_ORDERS, "DISABLED")
        self.assertEqual(PHASE65, "NOT_STARTED")
        self.assertEqual(UNAPPROVED, "UNAPPROVED")

    def test_null(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)


class TestEvidenceTypes(unittest.TestCase):
    def test_inventory_tags(self):
        inv = build_evidence_inventory()
        types = {i["evidence_type"] for i in inv["items"]}
        self.assertIn(LIVE_ACCOUNT, types)
        self.assertIn(USER_REPORTED, types)
        self.assertIn(SYNTHETIC_TEST, types)
        for i in inv["items"]:
            if i["evidence_type"] in {SYNTHETIC_TEST, USER_REPORTED}:
                self.assertFalse(i["usable_as_account_execution_fact"])

    def test_account_specific_vs_published(self):
        c = investigate_commission_boundary()
        self.assertFalse(c["merged"])
        self.assertEqual(c["account_specific"]["status"], UNKNOWN)
        self.assertFalse(c["published"]["mapped_to_trial15_xauusdm"])


class TestBlockers(unittest.TestCase):
    def test_unknown_commission_blocking(self):
        c = investigate_commission_boundary(n_trade_deals=0)
        self.assertEqual(c["current_state"], UNKNOWN)
        self.assertFalse(c["can_close_without_fill"])
        self.assertEqual(c["classification"], REQUIRES_GENUINE_ACCOUNT_EVENT)

    def test_calculated_vs_broker_observed_margin(self):
        m = build_margin_boundary()
        self.assertEqual(m["layers"]["A_broker_observed"]["evidence_type"], LIVE_ACCOUNT)
        self.assertFalse(m["layers"]["C_leverage_estimate"]["usable_as_broker_fact"])
        self.assertEqual(m["classification"], STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT)
        self.assertEqual(m["order_calc_margin"], "PROHIBITED_NOT_INVOKED")

    def test_session_evidence_classification(self):
        s = investigate_session_boundary()
        self.assertFalse(s["inferred_from_gaps"])
        self.assertEqual(s["classification"], CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE)
        self.assertTrue(s["can_close_without_fill"])
        self.assertEqual(s["current_state"], UNKNOWN)

    def test_swap_conflict_preservation(self):
        sw = forensic_swap_reconciliation()
        self.assertFalse(sw["overwrite"])
        self.assertFalse(sw["reconciled"])
        self.assertEqual(sw["forensic_table"][0]["value"], SWAP_LONG_PHASE63)
        self.assertEqual(sw["forensic_table"][1]["value"], SWAP_LONG_PHASE64_7)
        self.assertEqual(sw["current_state"], "UNKNOWN_FOR_EXECUTION")


class TestCostAndRisk(unittest.TestCase):
    def test_cost_taxonomy(self):
        tax = build_cost_taxonomy()
        self.assertEqual(len(tax["costs"]), 7)
        self.assertFalse(tax["COST_MODEL_VALIDATED"])
        self.assertEqual(tax["current_state"], "INCOMPLETE")

    def test_unknown_cost_propagation(self):
        tax = build_cost_taxonomy()
        commission = next(x for x in tax["costs"] if x["cost"] == "commission")
        self.assertFalse(commission["demo_risk_gating_eligible"])
        self.assertEqual(commission["verification_status"], UNKNOWN)

    def test_conservative_bounded_cost(self):
        tax = build_cost_taxonomy()
        spread = next(x for x in tax["costs"] if x["cost"] == "spread")
        self.assertTrue(spread["demo_risk_gating_eligible"])
        self.assertTrue(tax["conservative_bounds"]["commission"].startswith("NOT_SAFELY"))

    def test_risk_policy_dependency_blocking(self):
        pol = build_risk_policy_evidence()
        self.assertEqual(pol["overall_approval_status"], UNAPPROVED)
        self.assertIn("margin_safety_threshold", pol["blocked_parameters"])
        self.assertTrue(any(p["status"] == BLOCKED_BY_UNKNOWN for p in pol["parameters"]))
        self.assertFalse(pol["authorizes_execution"])


class TestMatrix(unittest.TestCase):
    def test_matrix_consistency(self):
        m = build_evidence_boundary_matrix()
        self.assertTrue(m["matrix_consistent"])
        self.assertFalse(m["forced_closure"])
        blockers = {r["blocker"] for r in m["rows"]}
        for b in ("Commission", "Margin", "Sessions", "Swap", "Cost model", "Risk policy"):
            self.assertIn(b, blockers)
        for r in m["rows"]:
            self.assertIn(r["classification"], BOUNDARY_CLASSES)
            self.assertTrue(r["next_evidence"])

    def test_risk_still_unapproved(self):
        m = build_evidence_boundary_matrix()
        self.assertEqual(m["artifacts"]["risk_policy"]["overall_approval_status"], UNAPPROVED)
        self.assertFalse(m["artifacts"]["cost"]["COST_MODEL_VALIDATED"])


class TestSuites(unittest.TestCase):
    def test_adversarial(self):
        s = run_adversarial_tests()
        self.assertTrue(s["suite_pass"], s)

    def test_integrity(self):
        self.assertTrue(audit_integrity()["checks_pass"])

    def test_no_order_invariant(self):
        self.assertIn("order_send", PROHIBITED_MT5_API)
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertIs(BROKER_SUBMISSION_ENABLED, False)
        self.assertIs(BROKER_EXECUTION_AUTHORIZED, False)


if __name__ == "__main__":
    unittest.main()
