"""Twenty required Phase 11 tests. Synthetic fixtures never enter real stores."""

from __future__ import annotations

import unittest

from phase10.constants import SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.historical_store import HistoricalExperienceStore
from phase10.paper_simulator import PaperSimulator, PaperSimulatorError
from phase10.paper_store import PaperExperienceStore
from phase10.validation import SourceSeparationError
from phase11.compatibility_audit import audit_compatibility
from phase11.performance_summary import paper_performance, separate_summaries
from phase11.tests.factories import LABEL, SYNTHETIC, entry, hist_exp, paper_decision
from phase11.validation import snapshot_protected


class Phase11Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SYNTHETIC)
        self.assertIn("SYNTHETIC", LABEL)

    def test_01_historical_source_provenance(self):
        rec = hist_exp()
        self.assertEqual(rec.source_type, SOURCE_HISTORICAL)
        self.assertEqual(rec.decision.provenance, "synthetic_fixture")
        self.assertTrue(rec.experience_id.startswith("hist:"))

    def test_02_paper_source_provenance(self):
        d = paper_decision()
        self.assertEqual(d.source_type, SOURCE_PAPER)
        self.assertEqual(d.provenance, "synthetic_fixture")
        self.assertTrue(d.decision_id.startswith("paper:"))

    def test_03_historical_id_uniqueness(self):
        store = HistoricalExperienceStore()
        store.append(hist_exp("2026-06-19 10:00:00", "BUY"))
        store.append(hist_exp("2026-06-19 10:00:00", "SELL", outcome_end="2026-06-19 11:00:00"))
        with self.assertRaises(SourceSeparationError):
            store.append(hist_exp("2026-06-19 10:00:00", "BUY"))

    def test_04_paper_id_uniqueness(self):
        store = PaperExperienceStore()
        store.record_decision(paper_decision("2026-06-19 10:00:00"))
        with self.assertRaises(SourceSeparationError):
            store.record_decision(paper_decision("2026-06-19 10:00:00"))

    def test_05_cross_source_separation(self):
        hist = HistoricalExperienceStore()
        paper = PaperExperienceStore()
        with self.assertRaises(SourceSeparationError):
            hist.append(paper_decision())  # type: ignore[arg-type]
        with self.assertRaises(SourceSeparationError):
            paper.record_decision(hist_exp())  # type: ignore[arg-type]
        with self.assertRaises(SourceSeparationError):
            paper.reject_historical(hist_exp())

    def test_06_historical_buy_sell_distinction(self):
        buy = hist_exp(side="BUY")
        sell = hist_exp("2026-06-19 10:05:00", "SELL", outcome_end="2026-06-19 11:05:00")
        self.assertEqual(buy.decision.side, "BUY")
        self.assertEqual(sell.decision.side, "SELL")
        self.assertNotEqual(buy.experience_id, sell.experience_id)

    def test_07_paper_buy_sell_wait_distinction(self):
        wait = paper_decision(raw="WAIT", final="WAIT", gate="ALLOW")
        blocked = paper_decision("2026-06-19 10:05:00", raw="BUY", final="WAIT", gate="BLOCK")
        allowed = paper_decision("2026-06-19 10:10:00", raw="SELL", final="SELL", gate="ALLOW")
        self.assertEqual(wait.raw_proposed_action, "WAIT")
        self.assertFalse(wait.is_executable)
        self.assertFalse(blocked.is_executable)
        self.assertTrue(allowed.is_executable)

    def test_08_wait_cannot_become_paper_trade(self):
        store = PaperExperienceStore()
        d = paper_decision(raw="WAIT", final="WAIT", gate="ALLOW")
        store.record_decision(d)
        with self.assertRaises(PaperSimulatorError):
            PaperSimulator(store).open_trade(d, entry())
        self.assertEqual(store.trade_count(), 0)

    def test_09_blocked_cannot_become_paper_trade(self):
        store = PaperExperienceStore()
        d = paper_decision(raw="BUY", final="WAIT", gate="BLOCK")
        store.record_decision(d)
        with self.assertRaises(PaperSimulatorError):
            PaperSimulator(store).open_trade(d, entry())
        self.assertEqual(store.trade_count(), 0)

    def test_10_missing_paper_outcome_remains_unavailable(self):
        store = PaperExperienceStore()
        store.record_decision(paper_decision())
        self.assertEqual(store.query_completed("2026-06-19 12:00:00"), [])
        perf = paper_performance(store, as_of="2026-06-19 12:00:00")
        self.assertIsNone(perf["mean_net_r"])
        self.assertEqual(perf["metrics_status"], "unavailable")

    def test_11_incomplete_outcome_exclusion(self):
        store = PaperExperienceStore()
        d = paper_decision(raw="BUY", final="BUY", gate="ALLOW")
        store.record_decision(d)
        PaperSimulator(store).open_trade(d, entry())
        self.assertEqual(store.completed_count("2026-06-19 12:00:00"), 0)

    def test_12_future_outcome_exclusion(self):
        store = HistoricalExperienceStore()
        store.append(hist_exp(outcome_end="2026-06-19 11:00:00"))
        self.assertEqual(len(store.query("2026-06-19 10:30:00")), 0)

    def test_13_equal_timestamp_exclusion(self):
        store = HistoricalExperienceStore()
        store.append(hist_exp(outcome_end="2026-06-19 11:00:00"))
        self.assertEqual(len(store.query("2026-06-19 11:00:00")), 0)
        self.assertEqual(len(store.query("2026-06-19 11:00:01")), 1)

    def test_14_as_of_retrieval_for_each_source(self):
        hist = HistoricalExperienceStore()
        hist.append(hist_exp("2026-06-19 10:00:00", "BUY", outcome_end="2026-06-19 11:00:00"))
        hist.append(hist_exp("2026-06-19 10:05:00", "SELL", outcome_end="2026-06-19 11:05:00"))
        paper = PaperExperienceStore()
        paper.record_decision(paper_decision("2026-06-19 10:00:00"))
        self.assertEqual(len(hist.query("2026-06-19 11:01:00")), 1)
        self.assertEqual(len(hist.query("2026-06-19 11:06:00")), 2)
        self.assertEqual(paper.query_completed("2026-06-19 11:06:00"), [])

    def test_15_read_only_compatibility_audit(self):
        hist = HistoricalExperienceStore()
        hist.append(hist_exp())
        paper = PaperExperienceStore()
        paper.record_decision(paper_decision())
        n_h, n_p = len(hist), paper.decision_count()
        report = audit_compatibility(hist, paper)
        self.assertFalse(report["merged_records"])
        self.assertFalse(report["normalized_in_place"])
        self.assertFalse(report["combined_learning_implemented"])
        self.assertTrue(report["explicit_adapter_required"])
        self.assertEqual(len(hist), n_h)
        self.assertEqual(paper.decision_count(), n_p)

    def test_16_historical_and_paper_metrics_remain_separate(self):
        hist = HistoricalExperienceStore()
        hist.append(hist_exp(net_r=1.0))
        paper = PaperExperienceStore()
        paper.record_decision(paper_decision())
        summary = separate_summaries(hist, paper, as_of="2026-06-19 12:00:00")
        self.assertIn("historical", summary)
        self.assertIn("paper", summary)
        self.assertFalse(summary["compared_as_equivalent_populations"])
        self.assertNotEqual(summary["historical"]["mean_net_r"], summary["paper"]["mean_net_r"])

    def test_17_empty_paper_metrics_return_null_unavailable(self):
        paper = PaperExperienceStore()
        paper.record_decision(paper_decision())
        perf = paper_performance(paper, as_of="2026-06-19 12:00:00")
        self.assertIsNone(perf["mean_net_r"])
        self.assertIsNone(perf["median_net_r"])
        self.assertIsNone(perf["profit_factor"])
        self.assertIsNone(perf["win_rate"])
        self.assertEqual(perf["metrics_status"], "unavailable")
        self.assertTrue(perf["unavailable_not_replaced_with_zero"])
        self.assertEqual(perf["completed_paper_outcomes"], 0)

    def test_18_no_fabricated_paper_records(self):
        from phase11.validation import load_real_stores
        state = load_real_stores()
        paper = state["paper"]
        self.assertEqual(paper.trade_count(), 0)
        self.assertEqual(paper.completed_count(state["as_of"]), 0)
        self.assertEqual(len(paper._trades), 0)
        self.assertEqual(len(paper._outcomes), 0)

    def test_19_deterministic_report_generation(self):
        hist = HistoricalExperienceStore()
        hist.append(hist_exp())
        paper = PaperExperienceStore()
        paper.record_decision(paper_decision())
        a = audit_compatibility(hist, paper)
        b = audit_compatibility(hist, paper)
        self.assertEqual(a, b)
        sa = separate_summaries(hist, paper, as_of="2026-06-19 12:00:00")
        sb = separate_summaries(hist, paper, as_of="2026-06-19 12:00:00")
        self.assertEqual(sa, sb)

    def test_20_protected_phase_1_10_artifact_integrity(self):
        snap = snapshot_protected()
        self.assertTrue(all(v["unchanged"] for v in snap.values()))
        self.assertGreaterEqual(len(snap), 18)


if __name__ == "__main__":
    unittest.main()
