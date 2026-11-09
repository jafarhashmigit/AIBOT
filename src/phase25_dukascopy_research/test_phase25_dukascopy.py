"""Phase 25 tests — offline units + optional raw presence."""

from __future__ import annotations

import struct
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase25.candles import build_m5_from_ticks
from phase25.constants import FROZEN_TOLERANCES, RESEARCH_CUTOFF_UTC
from phase25.download import bi5_url, decode_ticks
from phase25.integrity import protected_hashes_report
from phase25.live_feed import assess_live_feed


class Phase25Tests(unittest.TestCase):
    def test_01_tolerances_frozen_present(self):
        self.assertLessEqual(FROZEN_TOLERANCES["median_abs_close_usd"], 0.50)
        self.assertEqual(FROZEN_TOLERANCES["price_side_for_primary"], "mid")
        self.assertIn("freeze_note", FROZEN_TOLERANCES)

    def test_02_bi5_url_zero_based_month(self):
        # March = month 02 zero-based
        url = bi5_url("2026-03-10", 12)
        self.assertIn("/2026/02/10/12h_ticks.bi5", url)
        self.assertEqual(RESEARCH_CUTOFF_UTC, "2026-09-29 18:50:00")

    def test_03_decode_and_m5_no_fabricate(self):
        # Synthetic one-hour payload
        import lzma

        hour_start_ms = 0
        rec = struct.Struct(">IIIff")
        chunks = []
        # two ticks in minute 0 and minute 6 -> two M5 bars; gap at 05 not fabricated from nothing
        for ms, bid_i, ask_i in ((100, 5000000, 5000100), (6 * 60_000 + 100, 5000200, 5000300)):
            chunks.append(rec.pack(ms, ask_i, bid_i, 1.0, 1.0))
        body = lzma.compress(b"".join(chunks))
        ticks = decode_ticks(body, day="2026-03-10", hour=12)
        self.assertEqual(len(ticks), 2)
        candles = build_m5_from_ticks(ticks, side="mid")
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].timestamp_utc, "2026-03-10 12:00:00")
        self.assertEqual(candles[1].timestamp_utc, "2026-03-10 12:05:00")

    def test_04_live_unavailable(self):
        live = assess_live_feed()
        self.assertEqual(live["status"], "DUKASCOPY_LIVE_UNAVAILABLE")
        self.assertFalse(live["historical_implies_live"])

    def test_05_hashes_and_safety(self):
        h = protected_hashes_report()
        self.assertTrue(h["all_ok"])
        self.assertTrue(h["frozen_thresholds_intact"])
        self.assertEqual(h["safety"]["mt5_connections"], 0)
        self.assertEqual(h["safety"]["discord_messages_sent"], 0)

    def test_06_docs_exist(self):
        root = Path(__file__).resolve().parents[3]
        for name in (
            "PHASE_25_DUKASCOPY_ACQUISITION.md",
            "PHASE_25_MT5_PARITY.md",
            "PHASE_25_LIVE_FEED_ASSESSMENT.md",
        ):
            self.assertTrue((root / "docs" / "agent" / name).is_file(), msg=name)


if __name__ == "__main__":
    unittest.main()
