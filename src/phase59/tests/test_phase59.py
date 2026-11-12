"""Phase59 integrity tests — economics honesty."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from phase54.decision import NullPolicy
from phase59.constants import EXPECTED_NULL_POLICY, PHASE58_SPLITS, PROJECT_ROOT
from phase59.costs import build_cost_classification
from phase59.coverage import build_coverage_manifest
from phase59.inventory import build_inventory, phase58_holdout
from phase59.sufficiency import choose_verdict


class TestNullAndHoldout(unittest.TestCase):
    def test_null_policy(self):
        self.assertEqual(NullPolicy().version, EXPECTED_NULL_POLICY)

    def test_holdout_present(self):
        h = phase58_holdout()
        self.assertTrue(len(h) >= 1)
        if PHASE58_SPLITS.is_file():
            splits = json.loads(PHASE58_SPLITS.read_text(encoding="utf-8"))
            self.assertEqual(h, splits.get("holdout_sealed"))


class TestCosts(unittest.TestCase):
    def test_commission_slippage_unknown(self):
        c = build_cost_classification()
        by = {x["component"]: x for x in c["components"]}
        self.assertEqual(by["commission"]["classification"], "UNKNOWN")
        self.assertEqual(by["slippage"]["classification"], "UNKNOWN")
        self.assertTrue(by["commission"]["must_not_treat_as_zero"])
        obs = c["scenarios_from_phase46"]["OBSERVED_BIDASK_ONLY"]
        self.assertIsNone(obs["commission_usd_per_side"])
        self.assertIsNone(obs["slippage_usd_per_side"])


class TestInventory(unittest.TestCase):
    def test_union_nonempty(self):
        inv = build_inventory()
        self.assertGreater(inv["union_n_days"], 0)


class TestCoverage(unittest.TestCase):
    def test_coverage_manifest_no_silent_repair(self):
        inv = build_inventory()
        integrity = {"n_ok": 1, "n_days": 1, "total_m5_bars": 10, "total_ticks": 100, "rows": []}
        m = build_coverage_manifest(
            inv,
            integrity,
            research_days=[],
            stress_days=[],
            wait_days=[],
            holdout=phase58_holdout(),
        )
        self.assertFalse(m["source_data_silently_repaired"])
        self.assertIn("coverage_sha256", m)


class TestVerdictRules(unittest.TestCase):
    def test_partial_when_unknown_costs(self):
        v, _ = choose_verdict(
            integrity={"n_days": 10, "n_ok": 8},
            spread={"observable_bars": 5000},
            sufficiency={"critical_unknowns_insufficient": [{"capability": "commission_adjusted_evaluation"}]},
            holdout_sealed=True,
        )
        self.assertEqual(v, "EXECUTION_ECONOMICS_PARTIAL")


if __name__ == "__main__":
    unittest.main()
