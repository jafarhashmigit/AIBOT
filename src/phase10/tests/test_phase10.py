"""Eighteen required Phase 10 tests. Synthetic fixtures only for simulator paths."""

from __future__ import annotations

import unittest

from phase6.information_boundary import InformationBoundaryError
from phase10.constants import SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.experience_intelligence import ExperienceIntelligence
from phase10.historical_schema import HistoricalDecisionFields
from phase10.historical_store import HistoricalExperienceStore
from phase10.paper_schema import PaperDecision, PaperOutcome, PaperTrade
from phase10.paper_simulator import (
    PaperSimulator,
    PaperSimulatorError,
    assert_no_broker_surface,
    broker_order_calls,
    live_market_connections,
)
from phase10.paper_store import PaperExperienceStore
from phase10.tests.factories import entry, hist_exp, paper_decision
from phase10.validation import (
    SourceSeparationError,
    TemporalSafetyError,
    snapshot_protected,
)


class Phase10Tests(unittest.TestCase):
    def test_01_historical_schema_validation(self):
        rec = hist_exp()
        self.assertEqual(rec.source_type, SOURCE_HISTORICAL)
        self.assertEqual(rec.decision.side, "BUY")
        self.assertTrue(rec.experience_id.startswith("hist:"))
        payload = rec.decision.to_mapping()
        self.assertNotIn("actual_net_r", payload)
        self.assertNotIn("outcome_end", payload)

    def test_02_paper_schema_validation(self):
        d = paper_decision()
        self.assertEqual(d.source_type, SOURCE_PAPER)
        self.assertTrue(d.decision_id.startswith("paper:"))
        self.assertFalse(d.is_executable)
        from phase10.validation import assert_no_outcome_keys
        with self.assertRaises(InformationBoundaryError):
            assert_no_outcome_keys({"decision_id": d.decision_id, "actual_net_r": 1.0})

    def test_03_explicit_source_type_enforcement(self):
        with self.assertRaises(SourceSeparationError):
            HistoricalDecisionFields(
                experience_id="hist:2026-06-19 10:00:00:BUY",
                source_type="MERGED",
                decision_timestamp="2026-06-19 10:00:00",
                side="BUY",
                fold_id="WF1",
                model_id="x",
                p_tp_rf=0.4,
                p_sl_rf=0.3,
                p_time_rf=0.3,
                pred_r_rf=0.1,
                pred_r_ridge=0.05,
                provenance="x",
            )
        with self.assertRaises(SourceSeparationError):
            paper_decision().__class__(
                **{**paper_decision().to_mapping(), "source_type": ""}
            )

    def test_04_historical_paper_cross_write_rejection(self):
        hist = HistoricalExperienceStore()
        paper = PaperExperienceStore()
        with self.assertRaises(SourceSeparationError):
            hist.append(paper_decision())  # type: ignore[arg-type]
        with self.assertRaises(SourceSeparationError):
            paper.reject_historical(hist_exp())
        with self.assertRaises(SourceSeparationError):
            paper.record_decision(hist_exp())  # type: ignore[arg-type]

    def test_05_cross_source_identifier_collision_rejection(self):
        with self.assertRaises(ValueError):
            PaperDecision(**{**paper_decision().to_mapping(), "decision_id": "hist:collision"})
        hist = HistoricalExperienceStore()
        hist.append(hist_exp())
        with self.assertRaises(SourceSeparationError):
            hist.append(hist_exp())

    def test_06_decision_outcome_field_separation(self):
        rec = hist_exp()
        self.assertNotIn("actual_net_r", rec.decision.to_mapping())
        self.assertIn("actual_net_r", rec.outcome.to_mapping())
        d = paper_decision()
        self.assertNotIn("simulated_realized_r", d.to_mapping())

    def test_07_future_outcome_exclusion(self):
        store = HistoricalExperienceStore()
        store.append(hist_exp())
        visible = store.query("2026-06-19 10:30:00")
        self.assertEqual(len(visible), 0)
        later = store.query("2026-06-19 11:05:00")
        self.assertEqual(len(later), 1)

    def test_08_strict_equal_timestamp_boundary(self):
        store = HistoricalExperienceStore()
        store.append(hist_exp(outcome_end="2026-06-19 11:00:00"))
        self.assertEqual(len(store.query("2026-06-19 11:00:00")), 0)
        self.assertEqual(len(store.query("2026-06-19 11:00:01")), 1)

    def test_09_incomplete_outcome_exclusion(self):
        paper = PaperExperienceStore()
        d = paper_decision(raw="BUY", final="BUY", gate="ALLOW")
        paper.record_decision(d)
        sim = PaperSimulator(paper)
        trade = sim.open_trade(d, entry())
        self.assertEqual(paper.completed_count("2026-06-19 12:00:00"), 0)
        self.assertEqual(trade.execution_status, "open_simulated")

    def test_10_chronological_insertion(self):
        store = HistoricalExperienceStore()
        store.append(hist_exp("2026-06-19 10:05:00", outcome_end="2026-06-19 11:05:00"))
        with self.assertRaises(TemporalSafetyError):
            store.append(hist_exp("2026-06-19 10:00:00", outcome_end="2026-06-19 11:00:00"))
        paper = PaperExperienceStore()
        paper.record_decision(paper_decision("2026-06-19 10:05:00"))
        with self.assertRaises(TemporalSafetyError):
            paper.record_decision(paper_decision("2026-06-19 10:00:00"))

    def test_11_read_only_intelligence_interface(self):
        hist = HistoricalExperienceStore()
        hist.append(hist_exp())
        paper = PaperExperienceStore()
        intel = ExperienceIntelligence(hist, paper)
        summary = intel.summary("2026-06-19 12:00:00")
        self.assertIn("historical", summary)
        self.assertIn("paper", summary)
        self.assertFalse(summary["merged_raw_records"])
        self.assertFalse(summary["makes_trading_decisions"])
        intel.assert_read_only()
        self.assertFalse(hasattr(intel, "append"))

    def test_12_as_of_timestamp_retrieval(self):
        hist = HistoricalExperienceStore()
        hist.append(hist_exp("2026-06-19 10:00:00", outcome_end="2026-06-19 11:00:00"))
        hist.append(hist_exp("2026-06-19 10:05:00", "SELL", outcome_end="2026-06-19 11:05:00"))
        intel = ExperienceIntelligence(hist, PaperExperienceStore())
        early = intel.summary("2026-06-19 11:01:00")
        later = intel.summary("2026-06-19 11:06:00")
        self.assertEqual(early["historical"]["record_count"], 1)
        self.assertEqual(later["historical"]["record_count"], 2)

    def test_13_deterministic_summaries(self):
        hist = HistoricalExperienceStore()
        hist.append(hist_exp())
        hist.append(hist_exp("2026-06-19 10:05:00", "SELL", outcome_end="2026-06-19 11:05:00"))
        intel = ExperienceIntelligence(hist, PaperExperienceStore())
        a = intel.summary("2026-06-19 12:00:00")
        b = intel.summary("2026-06-19 12:00:00")
        self.assertEqual(a, b)

    def test_14_wait_cannot_create_paper_trade(self):
        paper = PaperExperienceStore()
        d = paper_decision(raw="WAIT", final="WAIT", gate="ALLOW")
        paper.record_decision(d)
        sim = PaperSimulator(paper)
        with self.assertRaises(PaperSimulatorError):
            sim.open_trade(d, entry())

    def test_15_blocked_action_cannot_create_paper_trade(self):
        paper = PaperExperienceStore()
        d = paper_decision(raw="BUY", final="WAIT", gate="BLOCK")
        paper.record_decision(d)
        sim = PaperSimulator(paper)
        with self.assertRaises(PaperSimulatorError):
            sim.open_trade(d, entry())

    def test_16_paper_outcome_attaches_only_after_completion(self):
        paper = PaperExperienceStore()
        d = paper_decision(raw="SELL", final="SELL", gate="ALLOW")
        paper.record_decision(d)
        sim = PaperSimulator(paper)
        trade = sim.open_trade(d, entry())
        with self.assertRaises(TemporalSafetyError):
            sim.complete_trade(
                trade,
                as_of="2026-06-19 11:00:00",
                exit_timestamp="2026-06-19 11:00:00",
                exit_price=2290.0,
                exit_reason="SL",
                realized_r=-1.0,
                net_pnl=-2.0,
                provenance="synthetic_fixture",
            )
        outcome = sim.complete_trade(
            trade,
            as_of="2026-06-19 11:05:00",
            exit_timestamp="2026-06-19 11:00:00",
            exit_price=2290.0,
            exit_reason="SL",
            realized_r=-1.0,
            net_pnl=-2.0,
            provenance="synthetic_fixture",
        )
        self.assertEqual(outcome.outcome_status, "completed")
        self.assertEqual(len(paper.query_completed("2026-06-19 11:05:00")), 1)

    def test_17_no_broker_order_functions_are_called(self):
        assert_no_broker_surface()
        self.assertEqual(broker_order_calls(), 0)
        self.assertEqual(live_market_connections(), 0)
        import sys
        self.assertNotIn("MetaTrader5", sys.modules)

    def test_18_protected_phase_1_9_artifacts_remain_unchanged(self):
        snap = snapshot_protected()
        self.assertTrue(all(v["unchanged"] for v in snap.values()))
        self.assertGreaterEqual(len(snap), 12)


if __name__ == "__main__":
    unittest.main()
