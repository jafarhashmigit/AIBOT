"""Global UTC/PKT timestamp labeling standard tests."""

from __future__ import annotations

import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aibot_time import (
    TimestampDisplayError,
    assert_labeled,
    display_pkt,
    display_pkt_iso,
    display_utc,
    display_utc_iso,
    storage_utc_iso,
    storage_utc_wall,
    utc_to_pkt_offset_ok,
)
from phase16b.formatter import format_experimental_buy
from phase17.shadow_messages import build_shadow_payload
from phase18.messages import build_outcome_payload, build_signal_payload
from phase19.synthetic_messages import build_synthetic_signal_payload
from phase20.candles import enrich_observation_timestamps
from phase20.messages import build_shadow_outcome_payload, build_shadow_signal_payload


# Unlabeled wall-clock appearing after a timestamp-ish key in user templates.
_UNLABELED_ASSIGN = re.compile(
    r"(?i)(timestamp|candle_close|signal time|outcome time|decision_timestamp|generated_at)"
    r"[^\n]{0,40}?"
    r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?!Z)(?!\s*UTC)(?!\s*PKT)(?!\+05:00)"
)


class AibotTimeTests(unittest.TestCase):
    def test_utc_always_labeled(self):
        s = display_utc("2026-11-09 13:45:00")
        self.assertEqual(s, "2026-11-09 13:45:00 UTC")
        assert_labeled(s)

    def test_pkt_always_labeled(self):
        s = display_pkt("2026-11-09 13:45:00")
        self.assertEqual(s, "2026-11-09 18:45:00 PKT")
        assert_labeled(s)

    def test_utc_to_pkt_exactly_plus_five(self):
        self.assertTrue(utc_to_pkt_offset_ok("2026-11-09 13:45:00"))
        self.assertEqual(display_pkt("2026-11-09 13:45:00"), "2026-11-09 18:45:00 PKT")
        self.assertEqual(display_utc_iso("2026-11-09 13:45:00"), "2026-11-09T13:45:00Z (UTC)")
        self.assertEqual(display_pkt_iso("2026-11-09 13:45:00"), "2026-11-09T18:45:00+05:00 (PKT)")

    def test_storage_unchanged_unlabeled(self):
        self.assertEqual(storage_utc_wall("2026-11-09 13:45:00"), "2026-11-09 13:45:00")
        self.assertEqual(storage_utc_iso("2026-11-09 13:45:00"), "2026-11-09T13:45:00Z")
        self.assertFalse(storage_utc_wall("2026-11-09 13:45:00").endswith("UTC"))

    def test_refuse_ambiguous_naive_without_established_tz(self):
        naive = datetime(2026, 11, 9, 13, 45, 0)  # no tzinfo
        with self.assertRaises(TimestampDisplayError):
            display_utc(naive, naive_means="unknown")

    def test_enrich_keeps_raw_utc_storage(self):
        bar = {
            "bar_open_timestamp_utc": "2026-11-09 12:00:00",
            "bar_close_timestamp_utc": "2026-11-09 12:05:00",
        }
        ts = enrich_observation_timestamps(bar)
        self.assertEqual(ts["candle_timestamp_utc"], "2026-11-09 12:05:00")
        self.assertTrue(ts["candle_timestamp_pkt"].endswith("PKT"))
        self.assertTrue(ts["candle_timestamp_utc_display"].endswith("UTC"))
        self.assertNotIn("UTC", ts["candle_timestamp_utc"])

    def test_discord_templates_labeled(self):
        decision = {
            "decision_id": "d1",
            "experimental_action": "BUY",
            "final_action": "WAIT",
            "decision_timestamp_utc": "2026-11-09 12:05:00",
            "candidate_status": "EXPERIMENTAL",
            "model_status": "NO_MODEL",
        }
        obs = {
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "bar_close_timestamp_utc": "2026-11-09 12:05:00",
            "close": 2000.0,
        }
        payloads = [
            build_shadow_payload(decision, obs)["content"],
            build_signal_payload(decision, obs)["content"],
            build_synthetic_signal_payload(decision, obs)["content"],
            build_shadow_signal_payload(decision, obs)["content"],
            format_experimental_buy(
                {
                    **decision,
                    "event_id": "e1",
                    "risk_gate_result": "BLOCK",
                    "decision_reason": "test",
                    "champion_status": "NO_MODEL",
                }
            )["content"],
        ]
        for content in payloads:
            self.assertRegex(content, r"\d{2}:\d{2}:\d{2} UTC|\d{2}:\d{2}:\d{2} PKT|\d{2}:\d{2} PKT")
            self.assertIsNone(_UNLABELED_ASSIGN.search(content), msg=content)

    def test_outcome_templates_labeled(self):
        outcome = {
            "decision_id": "d1",
            "outcome_event_id": "d1__H12",
            "symbol": "XAUUSD",
            "side": "BUY",
            "horizon_id": "H12",
            "horizon_label": "60M",
            "status": "PASS",
            "realized_r": "1.0",
            "decision_timestamp_utc": "2026-11-09 12:05:00",
            "outcome_timestamp_utc": "2026-11-09 13:05:00",
        }
        for content in (
            build_outcome_payload(outcome)["content"],
            build_shadow_outcome_payload(outcome)["content"],
        ):
            self.assertIn("UTC", content)
            self.assertIn("PKT", content)
            self.assertIsNone(_UNLABELED_ASSIGN.search(content), msg=content)

    def test_ids_and_storage_fields_not_rewritten_by_display(self):
        # Decision IDs embedding raw UTC must remain constructible from unlabeled storage.
        open_utc = "2026-11-09 17:05:00"
        dec_id = f"p28_H13C_BASELINE_{open_utc.replace(' ', 'T')}"
        self.assertEqual(dec_id, "p28_H13C_BASELINE_2026-11-09T17:05:00")
        self.assertEqual(storage_utc_wall(open_utc), open_utc)


if __name__ == "__main__":
    unittest.main()
