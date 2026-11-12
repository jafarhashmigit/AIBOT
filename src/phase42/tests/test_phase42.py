"""Phase 42 tests — leakage, determinism, protocol gates."""

from __future__ import annotations

import unittest

from phase42.constants import CHAMPION_STATUS, PRODUCTION_FINAL_ACTION, RECIPE_ID, RETIRED_CANDIDATES
from phase42.features import build_feature_rows
from phase42.hypotheses import frozen_hypothesis_registry
from phase42.labels import attach_forward_labels
from phase42.qualification import decide_verdict
from phase42.triggers import detect_events


class TestPolicy(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase42_"))
        self.assertIn("H13_C", RETIRED_CANDIDATES)
        self.assertIn("mean_reversion", RETIRED_CANDIDATES)

    def test_registry_families(self):
        reg = frozen_hypothesis_registry()
        self.assertEqual(reg["n_hypotheses"], 10)
        self.assertEqual(reg["n_families"], 10)
        ids = [h["id"] for h in reg["hypotheses"]]
        self.assertEqual(len(ids), len(set(ids)))


class TestFeatures(unittest.TestCase):
    def _bars(self, n=60):
        bars = []
        px = 2000.0
        for i in range(n):
            o = px
            h = px + 1.0
            l = px - 1.0
            c = px + (0.2 if i % 2 == 0 else -0.1)
            bars.append(
                {
                    "timestamp_utc": f"2026-01-15 {i // 12:02d}:{(i % 12) * 5:02d}:00",
                    "time_epoch": 1000 + i * 300,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                }
            )
            px = c
        return bars

    def test_determinism(self):
        bars = self._bars()
        h1 = []
        for d, base in (("2026-01-13", 0), ("2026-01-14", 24)):
            for h in range(24):
                h1.append(
                    {
                        "timestamp_utc": f"{d} {h:02d}:00:00",
                        "time_epoch": 500 + (base + h) * 3600,
                        "close": 1990.0 + base + h,
                    }
                )
        a = build_feature_rows(bars, h1, None)
        b = build_feature_rows(bars, h1, None)
        self.assertEqual(len(a), len(b))
        self.assertEqual(a[40]["compress_bars"], b[40]["compress_bars"])

    def test_no_future_labels_at_end(self):
        bars = self._bars(30)
        rows = attach_forward_labels(build_feature_rows(bars, [], None))
        self.assertIsNone(rows[-1]["ret_h12"])


class TestTriggers(unittest.TestCase):
    def test_displacement_trigger(self):
        rows = [
            {
                "time": "2026-01-15 12:00:00",
                "day": "2026-01-15",
                "bar_disp_atr": 2.0,
                "disp_sign": 1,
                "atr_14": 1.0,
                "close": 100.0,
            }
        ]
        ev = detect_events("H42_J_DISPLACEMENT_RETRACE", rows)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["side"], -1)


class TestVerdict(unittest.TestCase):
    def test_no_predictive(self):
        v = decide_verdict(
            {"results": [{"predictive_pass": False, "decision_value": False, "hypothesis_id": "x"}], "rejected": []},
            [],
            indep_ok=True,
        )
        self.assertEqual(v["final_verdict"], "NO_PREDICTIVE_VALUE")


if __name__ == "__main__":
    unittest.main()
