"""Prompt7 discovery safety & selection tests — no holdout peek, no fake survivor."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from signal_bot.discovery.audit import build_research_audit
from signal_bot.discovery.candidates import preregistered_candidates, select_candidate
from signal_bot.discovery.constants import (
    CHAMPION_STATUS,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_PROMISING,
)
from signal_bot.discovery.data_feasibility import build_data_feasibility
from signal_bot.discovery.evaluation import (
    build_statistical_evaluation,
    dual_experience_architecture_note,
)


class TestPrompt07Audit(unittest.TestCase):
    def test_no_accepted_edges(self) -> None:
        audit = build_research_audit()
        self.assertEqual(audit["n_accepted"], 0)
        self.assertFalse(audit["phase58_holdout_accessed"])
        self.assertTrue(audit["h70"]["revive_forbidden"])

    def test_retired_families_present(self) -> None:
        audit = build_research_audit()
        retired = set(audit["retired_do_not_revive"] or [])
        self.assertIn("H13_C", retired)
        self.assertIn("H42_A_VOL_COMPRESS_EXPAND", retired)
        self.assertIn("H42_C_SESSION_SWEEP_REJECT", retired)


class TestPrompt07Data(unittest.TestCase):
    def test_holdout_not_accessed(self) -> None:
        feas = build_data_feasibility()
        sealed = feas.get("sealed_inaccessible") or {}
        self.assertFalse(sealed.get("accessed"))
        self.assertFalse(feas.get("sufficient_for_independent_validation"))

    def test_phase53_marked_consumed(self) -> None:
        feas = build_data_feasibility()
        mq = feas.get("metaquotes_xauusd_archives") or {}
        self.assertTrue(mq.get("previously_consumed"))
        self.assertFalse(mq.get("independent_confirmation"))

    def test_does_not_load_holdout_results_file(self) -> None:
        """Guard: production discovery modules must not import/read holdout_results.json."""
        root = PROJECT_ROOT / "src" / "signal_bot" / "discovery"
        for p in root.glob("*.py"):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("holdout_results.json", text, msg=str(p))
            self.assertNotIn("phase58/holdout", text.replace("\\", "/"), msg=str(p))


class TestPrompt07Selection(unittest.TestCase):
    def test_candidates_preregistered(self) -> None:
        cands = preregistered_candidates()
        self.assertGreaterEqual(len(cands), 7)
        ids = {c["candidate_id"] for c in cands}
        self.assertIn("C07_A_SESSION_OPEN_DISCOVERY", ids)
        self.assertIn("C07_H_H70_REVIVAL", ids)

    def test_no_promising_without_independent_data(self) -> None:
        feas = build_data_feasibility()
        sel = select_candidate(feas)
        self.assertEqual(sel["primary_verdict"], VERDICT_INSUFFICIENT_DATA)
        self.assertIsNone(sel["surviving_candidate_id"])
        self.assertNotEqual(sel["primary_verdict"], VERDICT_PROMISING)
        self.assertEqual(sel["champion"], CHAMPION_STATUS)
        self.assertEqual(sel["production"], PRODUCTION_FINAL_ACTION)
        self.assertFalse(sel["independent_profitability_evidence"])
        self.assertEqual(sel["net_profitability"], "NOT_ESTABLISHED")
        self.assertIn("NONE", sel["implementation"])

    def test_h70_revival_rejected(self) -> None:
        cands = preregistered_candidates()
        h70 = next(c for c in cands if c["candidate_id"] == "C07_H_H70_REVIVAL")
        self.assertTrue(str(h70["preregister_disposition"]).startswith("REJECT"))

    def test_retired_family_candidates_rejected(self) -> None:
        for cid in (
            "C07_B_VOL_EXPANSION_AFTER_COMPRESSION",
            "C07_C_FAILED_AUCTION",
            "C07_D_TREND_PULLBACK_CONTINUATION",
        ):
            c = next(x for x in preregistered_candidates() if x["candidate_id"] == cid)
            self.assertTrue(str(c["preregister_disposition"]).startswith("REJECT"))


class TestPrompt07EvalAndSafety(unittest.TestCase):
    def test_no_new_edge_eval(self) -> None:
        feas = build_data_feasibility()
        sel = select_candidate(feas)
        ev = build_statistical_evaluation(sel, feas)
        self.assertEqual(ev["candidates_statistically_evaluated_as_new_edge"], 0)
        self.assertFalse(ev["independent_profitability_evidence"])
        self.assertFalse(ev["phase58_holdout_accessed"])
        costs = ev["cost_sensitivity"]
        self.assertFalse(costs["unknown_costs_treated_as_zero"])

    def test_dual_experience_separation(self) -> None:
        note = dual_experience_architecture_note()
        self.assertIn("source_1_historical_hypothetical", note)
        self.assertIn("source_2_actual_paper_decisions", note)
        self.assertIn("must_not_mix_with", note["source_2_actual_paper_decisions"])

    def test_no_strategy_policy_module_fabricated(self) -> None:
        """No artificial C07 policy package when no candidate survives."""
        policy_dir = PROJECT_ROOT / "src" / "signal_bot" / "discovery" / "policies"
        self.assertFalse(policy_dir.exists())

    def test_order_send_constant(self) -> None:
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")


class TestPrompt07HoldoutSealedOnDisk(unittest.TestCase):
    def test_holdout_file_untouched_by_selection(self) -> None:
        """Selection does not require reading sealed outcomes."""
        holdout = PROJECT_ROOT / "reports" / "phase58" / "holdout_results.json"
        # File may exist; we only assert our selection path doesn't need it.
        feas = {
            "sufficient_for_independent_validation": False,
            "genuine_live_exness_xauusdm": {"independent_complete_asia_london_dates": 0},
        }
        sel = select_candidate(feas)
        self.assertEqual(sel["primary_verdict"], VERDICT_INSUFFICIENT_DATA)
        if holdout.is_file():
            # Ensure discovery did not rewrite it
            before = holdout.stat().st_mtime
            select_candidate(feas)
            after = holdout.stat().st_mtime
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
