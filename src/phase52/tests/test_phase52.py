"""Phase52 scoring/qualification tests."""

from __future__ import annotations

import unittest

from phase52.qualification import choose_verdict
from phase52.scoring import score_combination


class TestScoring(unittest.TestCase):
    def test_unavailable_zero(self) -> None:
        sc = score_combination(
            rates={"ok": False, "n_bars": 0, "symbol": "X", "timeframe": "M5"},
            ticks=None,
            archive=None,
            symbol_meta={"available": False},
        )
        self.assertEqual(sc["score"], 0.0)
        self.assertFalse(sc["qualified"])

    def test_xau_archive_helps(self) -> None:
        sc = score_combination(
            rates={
                "ok": True,
                "n_bars": 10000,
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "n_gap_events": 5,
                "n_unique_hours": 22,
            },
            ticks={"bid_ask_available": True, "hours_ok": 3, "sample_hours": [8, 13, 18], "spread_median": 0.15, "spread_p95": 0.25, "crossed_quotes": 0},
            archive={
                "combined_unique_m5_days": 70,
                "sources": {"phase43": {"days_with_ge20_tick_hours": 30, "sample_spread_median": 0.15, "sample_spread_p95": 0.3}},
            },
            symbol_meta={"available": True},
        )
        self.assertGreaterEqual(sc["score"], 0.55)
        self.assertTrue(sc["qualified"])


class TestVerdict(unittest.TestCase):
    def test_selected(self) -> None:
        v, _ = choose_verdict(
            {
                "ranked": [{"symbol": "XAUUSD", "timeframe": "M5", "score": 0.8, "qualified": True}],
                "primary": {"symbol": "XAUUSD", "timeframe": "M5", "score": 0.8, "qualified": True},
            }
        )
        self.assertEqual(v, "MARKET_REPRESENTATION_SELECTED")


if __name__ == "__main__":
    unittest.main()
