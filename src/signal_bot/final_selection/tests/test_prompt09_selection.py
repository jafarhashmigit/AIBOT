"""Prompt9 selection safety — no forced champion, no holdout, unknown costs ≠ 0."""

from __future__ import annotations

import unittest

from signal_bot.final_selection.audit_matrix import build_candidate_evidence_matrix
from signal_bot.final_selection.c07_evaluation import evaluate_c07_a
from signal_bot.final_selection.constants import (
    CHAMPION_STATUS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    VERDICT_NONE,
    VERDICT_QUALIFIED,
)
from signal_bot.final_selection.selection import qualification_checklist, select_champion
from signal_bot.final_selection.validation import build_cost_and_risk_assessment, build_validation_results


class TestAuditMatrix(unittest.TestCase):
    def test_no_accepted_edges(self):
        m = build_candidate_evidence_matrix()
        self.assertEqual(m["n_accepted_validated_edges"], 0)
        self.assertFalse(m["data"]["phase58_holdout_accessed"])
        self.assertEqual(m["execution_economics"]["NET_PROFITABILITY"], "NOT_ESTABLISHED")


class TestC07(unittest.TestCase):
    def test_c07_unimplementable(self):
        c07 = evaluate_c07_a(live_complete_dates=0, live_m5=13)
        self.assertEqual(c07["disposition"], "REJECT_UNIMPLEMENTABLE")
        self.assertFalse(c07["implementable_from_evidence"])
        self.assertFalse(c07["exploratory_archive_screen_authorized"])
        self.assertFalse(c07["confirmatory_validation_run"])
        self.assertFalse(c07["strategy_module_created"])
        self.assertGreaterEqual(len(c07["unresolved_parameters"]), 5)

    def test_even_with_plenty_of_dates_still_unimplementable_without_freeze(self):
        c07 = evaluate_c07_a(live_complete_dates=50, live_m5=5000)
        self.assertEqual(c07["disposition"], "REJECT_UNIMPLEMENTABLE")
        self.assertFalse(c07["implementable_from_evidence"])


class TestSelection(unittest.TestCase):
    def test_no_qualified_strategy(self):
        m = build_candidate_evidence_matrix()
        econ = m["execution_economics"]
        c07 = evaluate_c07_a(
            live_complete_dates=int(m["data"]["complete_independent_asia_london_dates"] or 0),
            live_m5=int(m["data"]["live_m5"] or 0),
        )
        sel = select_champion(matrix=m, c07=c07, economics=econ)
        self.assertEqual(sel["primary_verdict"], VERDICT_NONE)
        self.assertIsNone(sel["champion_candidate_id"])
        self.assertEqual(sel["champion_status"], CHAMPION_STATUS)
        self.assertEqual(sel["production"], PRODUCTION_FINAL_ACTION)
        self.assertFalse(sel["thresholds_lowered"])
        self.assertNotEqual(sel["primary_verdict"], VERDICT_QUALIFIED)
        self.assertIn("NONE", sel["implementation"])

    def test_checklist_fails_without_net(self):
        c07 = evaluate_c07_a(live_complete_dates=0, live_m5=0)
        cl = qualification_checklist(c07, {"NET_PROFITABILITY": "NOT_ESTABLISHED"})
        self.assertFalse(cl["all_pass"])
        self.assertFalse(cl["checks"]["net_profitability_established"])


class TestValidationCostRisk(unittest.TestCase):
    def test_validation_no_holdout(self):
        c07 = evaluate_c07_a(live_complete_dates=0, live_m5=10)
        val = build_validation_results(
            c07=c07,
            economics={"NET_PROFITABILITY": "NOT_ESTABLISHED"},
            live={"n_complete_independent_live_dates": 0},
        )
        self.assertFalse(val["confirmatory_protocol"]["phase58_holdout_accessed"])
        self.assertFalse(val["cost_integration"]["unknown_commission_treated_as_zero"])

    def test_cost_risk_unapproved(self):
        cr = build_cost_and_risk_assessment(
            {"NET_PROFITABILITY": "NOT_ESTABLISHED", "spread_n": 100, "spread_median_price": 0.24},
            {"discord_actionable": "DISABLED"},
        )
        self.assertEqual(cr["risk_policy"], "UNAPPROVED")
        self.assertFalse(cr["unknown_costs_as_zero"])
        self.assertFalse(cr["production_cost_model_approved"])


class TestSafety(unittest.TestCase):
    def test_invariants(self):
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")

    def test_no_champion_policy_package(self):
        policies = PROJECT_ROOT / "src" / "signal_bot" / "final_selection" / "policies"
        self.assertFalse(policies.exists())

    def test_no_holdout_file_refs_in_package(self):
        root = PROJECT_ROOT / "src" / "signal_bot" / "final_selection"
        for p in root.glob("*.py"):
            self.assertNotIn("holdout_results.json", p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
