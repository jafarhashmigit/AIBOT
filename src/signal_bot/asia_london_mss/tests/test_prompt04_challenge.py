"""Prompt 4 challenge reproducibility / safety — no performance claims."""

from __future__ import annotations

import unittest

from signal_bot.asia_london_mss.challenge import (
    PHASE53_M5,
    _holdout_sealed,
    build_data_inventory,
    implementation_audit,
    load_jsonl_bars,
    replay_day,
    run_deterministic_twice,
    run_frozen_replay,
)
from signal_bot.asia_london_mss.constants import CHAMPION_STATUS, ORDER_SEND


class TestPrompt04Audit(unittest.TestCase):
    def test_implementation_matches_frozen_spec(self):
        audit = implementation_audit()
        self.assertFalse(audit["material_defect"])
        self.assertEqual(audit["result"], "MATCH_FROZEN_SPEC")

    def test_safety_invariants(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(ORDER_SEND, "PROHIBITED")


class TestPrompt04DataGates(unittest.TestCase):
    def test_holdout_not_in_eligible(self):
        inv = build_data_inventory()
        holdout = set(_holdout_sealed())
        eligible = set(inv["eligible_phase53_dates"])
        self.assertFalse(eligible & holdout)
        self.assertEqual(inv["independent_unconsumed_complete_days"], 0)
        self.assertEqual(inv["evidence_class"], "EXPLORATORY_RETROSPECTIVE_ONLY")

    def test_holdout_files_not_loaded_by_replay(self):
        holdout = _holdout_sealed()
        present = {p.stem.replace("m5_XAUUSD_", "") for p in PHASE53_M5.glob("m5_*.jsonl")}
        overlap = present & holdout
        self.assertTrue(len(overlap) >= 1)
        replay = run_frozen_replay()
        self.assertFalse(set(replay["dates"]) & holdout)
        self.assertFalse(replay["holdout_accessed"])


class TestPrompt04Replay(unittest.TestCase):
    def test_deterministic_dual_replay(self):
        det = run_deterministic_twice()
        self.assertTrue(
            det["identical"],
            msg=f"sha {det['ledger_sha256_a']} vs {det['ledger_sha256_b']}",
        )

    def test_no_duplicate_setup_ids_in_ledger(self):
        replay = run_frozen_replay()
        ids = [t["setup_id"] for t in replay["trades"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_chronological_trade_exits(self):
        replay = run_frozen_replay()
        for t in replay["trades"]:
            if t.get("mss_timestamp_utc") and t.get("exit_timestamp_utc"):
                self.assertLessEqual(t["mss_timestamp_utc"], t["exit_timestamp_utc"])

    def test_no_lookahead_window(self):
        days = build_data_inventory()["eligible_phase53_dates"]
        self.assertTrue(days)
        day = days[0]
        bars = load_jsonl_bars(PHASE53_M5 / f"m5_XAUUSD_{day}.jsonl")
        res = replay_day(
            bars,
            trading_date=day,
            dataset_id="test",
            provenance="TEST",
        )
        for t in res["trades"]:
            self.assertLess(t["decision_idx"], len(bars))
            if t.get("entry_idx") is not None:
                self.assertGreater(t["entry_idx"], t["decision_idx"])


if __name__ == "__main__":
    unittest.main()
