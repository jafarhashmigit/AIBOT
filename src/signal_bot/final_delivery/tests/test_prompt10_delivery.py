"""Prompt10 delivery — hard safety, ops status, no strategy promotion."""

from __future__ import annotations

import unittest

from signal_bot.final_delivery.constants import (
    CHAMPION_STATUS,
    HARD_BLOCK_ACTIONABLE_DISCORD,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROMPT09_VERDICT,
)
from signal_bot.final_delivery.ops_status import build_ops_snapshot_from_health, publish_operational_status
from signal_bot.final_delivery.safety_audit import run_safety_audit
from signal_bot.orchestrator.constants import HARD_BLOCK_ACTIONABLE_DISCORD as ORCH_HARD
from signal_bot.orchestrator.delivery import deliver_signal
from signal_bot.orchestrator.formatter import format_operational_status, format_signal_message
from signal_bot.orchestrator.gate import effective_operating_mode, evaluate_publication_gate


class TestHardSafety(unittest.TestCase):
    def test_invariants(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertEqual(PROMPT09_VERDICT, "NO_QUALIFIED_STRATEGY")
        self.assertTrue(HARD_BLOCK_ACTIONABLE_DISCORD)
        self.assertTrue(ORCH_HARD)

    def test_authorized_clamped(self):
        self.assertEqual(effective_operating_mode("AUTHORIZED"), "SHADOW")

    def test_gate_blocks_buy_with_flags(self):
        event = {
            "schema_version": "aibot_signal_event_v1",
            "signal_id": "x",
            "decision_id": "d",
            "strategy_id": "S",
            "strategy_version": "1",
            "symbol": "XAUUSDm",
            "timeframe": "M5",
            "direction": "BUY",
            "created_utc": "2026-11-12T09:00:00Z",
            "validation_status": "INDEPENDENTLY_VALIDATED",
            "risk_check_status": "APPROVED",
            "data_quality_status": "OK",
            "market_data_provenance": "BROKER_OBSERVED_LIVE_BAR",
            "stale": False,
            "forming_bar": False,
        }
        g = evaluate_publication_gate(event, mode="AUTHORIZED", publication_authorization_enabled=True)
        self.assertFalse(g["allowed"])
        self.assertTrue(any("hard_block" in r or "no_qualified" in r or "champion" in r for r in g["block_reasons"]))

    def test_delivery_hard_blocks_network_for_buy(self):
        event = {
            "signal_id": "buy1",
            "direction": "BUY",
            "symbol": "XAUUSDm",
            "timeframe": "M5",
            "strategy_id": "X",
            "strategy_version": "1",
            "validation_status": "INDEPENDENTLY_VALIDATED",
            "risk_check_status": "APPROVED",
            "publication_status": "ALLOWED",
            "actionable_discord": True,
            "created_utc": "2026-11-12T09:00:00Z",
        }
        out = deliver_signal(
            event,
            mode="AUTHORIZED",
            gate_allowed=True,
            transport=lambda *a, **k: (200, "ok"),
        )
        self.assertFalse(out.get("network_called"))
        self.assertEqual(out.get("status"), "HARD_BLOCKED_ACTIONABLE")


class TestOpsStatus(unittest.TestCase):
    def test_format_ops_not_actionable(self):
        msg = format_operational_status(
            {
                "event": "STARTED",
                "mt5_connection_state": "CONNECTED",
                "collector_status": "RUNNING",
                "last_quote_ts": "2026-11-12T09:00:00Z",
                "last_m5_ts": "2026-11-12T08:55:00Z",
                "data_freshness_sec": 12,
                "created_utc": "2026-11-12T09:00:00Z",
            }
        )
        self.assertEqual(msg["message_type"], "SYSTEM_STATUS")
        self.assertFalse(msg["actionable"])
        self.assertIn("WAIT", msg["content"])
        self.assertIn("NO_QUALIFIED_STRATEGY", msg["content"])
        self.assertNotIn("Entry:", msg["content"])
        self.assertNotIn("Stop Loss", msg["content"])

    def test_wait_formatter_not_trade(self):
        msg = format_signal_message(
            {
                "direction": "WAIT",
                "symbol": "XAUUSDm",
                "timeframe": "M5",
                "strategy_id": "null",
                "strategy_version": "1",
                "signal_id": "s",
                "decision_id": "d",
                "validation_status": "N/A",
                "risk_check_status": "UNAPPROVED",
                "publication_status": "BLOCKED",
                "created_utc": "2026-11-12T09:00:00Z",
            },
            gated=True,
        )
        self.assertEqual(msg["message_type"], "NON_ACTIONABLE_WAIT")
        self.assertIn("trading recommendation", msg["content"].lower())
        self.assertIn("not", msg["content"].lower())
        self.assertNotIn("Entry:", msg["content"])

    def test_publish_ops_shadow(self):
        snap = build_ops_snapshot_from_health(
            {"service_status": "RUNNING", "mt5_connection_state": "CONNECTED", "data_freshness_sec": 1},
            event="TEST",
        )
        out = publish_operational_status(snap, force_shadow=True)
        self.assertEqual(out["status"], "SHADOW_RECORDED")
        self.assertFalse(out["network_called"])
        self.assertEqual(out["message_type"], "SYSTEM_STATUS")


class TestSafetyAudit(unittest.TestCase):
    def test_audit_pass(self):
        a = run_safety_audit()
        self.assertTrue(a["all_invariants_hold"])
        self.assertTrue(a["authorized_mode_clamped_to_shadow"])
        self.assertTrue(a["gate_blocks_buy_despite_flags"])
        self.assertTrue(a["delivery_hard_blocks_actionable_network"])
        self.assertFalse(a["config_flag_bypass_possible"])
        self.assertTrue(a["audit_pass"])


if __name__ == "__main__":
    unittest.main()
