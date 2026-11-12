"""Phase 36 deterministic tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from phase36.acquisition import validate_ticks
from phase36.bootstrap import day_block_bootstrap
from phase36.constants import (
    EXCLUDED_EVAL_DAYS,
    FROZEN_MEAN_REVERSION_PARAMS,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    file_sha256,
)
from phase36.date_selection import select_independent_dates
from phase36.frozen_spec import register_frozen_experiment
from phase36.qualification import apply_gates

UTC = timezone.utc


class TestDateSelection(unittest.TestCase):
    def test_excludes_phase34_35_days(self):
        sel = select_independent_dates(20)
        self.assertTrue(set(sel["selected_dates"]).isdisjoint(EXCLUDED_EVAL_DAYS))
        self.assertEqual(sel["selected_dates"], select_independent_dates(20)["selected_dates"])
        self.assertLessEqual(len(sel["selected_dates"]), 20)


class TestFrozenSpec(unittest.TestCase):
    def test_registry(self):
        spec = register_frozen_experiment()
        self.assertTrue(spec["rules_locked"])
        self.assertEqual(spec["parameters"]["z_entry"], FROZEN_MEAN_REVERSION_PARAMS["z_entry"])
        self.assertTrue(all(spec["source_hashes"].values()))


class TestValidateTicks(unittest.TestCase):
    def test_crossed_fails(self):
        t = {
            "timestamp_utc": "2026-04-01 10:00:00",
            "epoch_ms": int(datetime(2026, 4, 1, 10, 0, tzinfo=UTC).timestamp() * 1000),
            "bid": 2.0,
            "ask": 1.0,
            "spread": -1.0,
        }
        self.assertFalse(validate_ticks([t])["pass"])

    def test_ok(self):
        t = {
            "timestamp_utc": "2026-04-01 10:00:00",
            "epoch_ms": int(datetime(2026, 4, 1, 10, 0, tzinfo=UTC).timestamp() * 1000),
            "bid": 1.0,
            "ask": 1.7,
            "spread": 0.7,
        }
        self.assertTrue(validate_ticks([t])["pass"])


class TestBootstrap(unittest.TestCase):
    def test_empty(self):
        r = day_block_bootstrap([])
        self.assertFalse(r["ok"])

    def test_runs(self):
        trades = [
            {"day": "2026-04-01", "status": "PASS", "net_r": 0.5},
            {"day": "2026-04-01", "status": "FAIL", "net_r": -1.0},
            {"day": "2026-04-02", "status": "PASS", "net_r": 0.2},
            {"day": "2026-04-03", "status": "TIMEOUT", "net_r": 0.1},
        ]
        r = day_block_bootstrap(trades, n_draws=200)
        self.assertTrue(r["ok"])
        self.assertIn("ci95_low", r)


class TestGates(unittest.TestCase):
    def test_insufficient_data(self):
        g = apply_gates(
            n_complete_days=3,
            evaluation={"view_a_bidask": {"n_resolved": 10, "mean_r": 0.1}, "chronological": {}, "buy_summary": {}, "sell_summary": {}, "view_c_stress_extra_005": {"mean_r": 0.05}},
            bootstrap={"ci95_excludes_zero": False, "dependent_on_one_exceptional_day": False},
            indep_cmp={"ok": True},
        )
        self.assertEqual(g["final_verdict"], "INSUFFICIENT_DATA")


class TestSafety(unittest.TestCase):
    def test_protected_and_wait(self):
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        rel = next(iter(PROTECTED_HASHES))
        self.assertEqual(file_sha256(PROJECT_ROOT / rel), PROTECTED_HASHES[rel])


if __name__ == "__main__":
    unittest.main()
