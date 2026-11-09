"""Phase 16B offline tests. No real Discord HTTP. No MT5."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from phase16b.adapter import DiscordNotifier, decision_to_event
from phase16b.client import post_webhook
from phase16b.constants import (
    CHAMPION_STATUS,
    EXPERIMENTAL_DISCLAIMER,
    REAL_DISCORD_SENDS,
)
from phase16b.dedupe import DeliveryLedger
from phase16b.formatter import build_payload, format_experimental_buy, format_wait
from phase16b.integrity import verify_protected_hashes
from phase16b.secrets import redact_secrets, safe_config_status, webhook_configured


class Phase16BTests(unittest.TestCase):
    def test_01_champion_unchanged(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(REAL_DISCORD_SENDS, 0)

    def test_02_wait_payload(self):
        event = decision_to_event(
            {
                "decision_id": "d_wait",
                "experimental_action": "WAIT",
                "final_action": "WAIT",
                "decision_reason": "none",
            }
        )
        payload = build_payload(event)
        self.assertIn("WAIT", payload["content"])
        self.assertNotIn("discord.com/api/webhooks", payload["content"])

    def test_03_experimental_buy_disclaimer(self):
        event = {
            "event_id": "d_buy",
            "decision_id": "d_buy",
            "experimental_action": "BUY",
            "final_action": "WAIT",
            "risk_gate_result": "BLOCK",
            "message_type": "EXPERIMENTAL_BUY",
        }
        payload = format_experimental_buy(event)
        self.assertIn(EXPERIMENTAL_DISCLAIMER, payload["content"])
        self.assertIn("EXPERIMENTAL BUY", payload["content"])
        self.assertIn("WAIT", payload["content"])

    def test_04_experimental_sell_disclaimer(self):
        event = {
            "event_id": "d_sell",
            "decision_id": "d_sell",
            "experimental_action": "SELL",
            "final_action": "WAIT",
            "message_type": "EXPERIMENTAL_SELL",
        }
        payload = build_payload(event)
        self.assertIn(EXPERIMENTAL_DISCLAIMER, payload["content"])
        self.assertIn("EXPERIMENTAL SELL", payload["content"])

    def test_05_duplicate_prevention(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DeliveryLedger(Path(tmp) / "ledger.jsonl")
            notifier = DiscordNotifier(
                ledger=ledger,
                dry_run=True,
                env={"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/test"},
            )
            event = decision_to_event(
                {
                    "decision_id": "dup1",
                    "experimental_action": "WAIT",
                    "final_action": "WAIT",
                }
            )
            # Force mark as sent
            ledger.record(event, {"status": "SENT", "attempts": 1})
            second = notifier.notify(event)
            self.assertEqual(second["status"], "SKIPPED_DUPLICATE")
            self.assertFalse(second["changed_decision"])

    def test_06_missing_webhook_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DeliveryLedger(Path(tmp) / "ledger.jsonl")
            notifier = DiscordNotifier(ledger=ledger, dry_run=False, env={})
            event = decision_to_event(
                {
                    "decision_id": "no_cfg",
                    "experimental_action": "WAIT",
                    "final_action": "WAIT",
                }
            )
            result = notifier.notify(event)
            self.assertEqual(result["status"], "FAILED_CONFIG")
            self.assertFalse(result["changed_decision"])
            self.assertFalse(webhook_configured(env={}))

    def test_07_http_failure_does_not_change_decision(self):
        def boom(url, body, timeout):
            return 500, "err"

        sleeps: list[float] = []
        result = post_webhook(
            "https://discord.com/api/webhooks/1/test",
            {"content": "x"},
            transport=boom,
            sleep_fn=sleeps.append,
            max_attempts=3,
            backoff=(0.01, 0.01),
        )
        self.assertEqual(result["status"], "FAILED_HTTP")
        self.assertEqual(result["attempts"], 3)
        self.assertFalse(result["changed_decision"])
        self.assertEqual(len(sleeps), 2)

    def test_08_timeout_retry_then_fail(self):
        def timeout_transport(url, body, timeout):
            raise TimeoutError("timed out")

        # post_webhook catches Exception inside loop via transport returning —
        # our default transport catches; custom transport that raises is caught by try in loop? 
        # Looking at client: transport is called inside try and exceptions set last_error.
        sleeps: list[float] = []
        result = post_webhook(
            "https://discord.com/api/webhooks/1/test",
            {"content": "x"},
            transport=timeout_transport,
            sleep_fn=sleeps.append,
            max_attempts=2,
            backoff=(0.01,),
        )
        self.assertEqual(result["status"], "FAILED_HTTP")
        self.assertFalse(result["changed_decision"])
        self.assertGreaterEqual(result["attempts"], 1)

    def test_09_secret_never_in_logs_or_redaction(self):
        secret = "https://discord.com/api/webhooks/999/super-secret-token-value"
        redacted = redact_secrets(f"failed posting to {secret}")
        self.assertNotIn("super-secret-token-value", redacted)
        self.assertIn("[REDACTED_DISCORD_WEBHOOK]", redacted)
        status = safe_config_status(env={"DISCORD_WEBHOOK_URL": secret})
        self.assertTrue(status["configured"])
        self.assertFalse(status["value_revealed"])
        dumped = str(status)
        self.assertNotIn("super-secret-token-value", dumped)

    def test_10_http_success_path(self):
        def ok(url, body, timeout):
            self.assertIn(b"content", body)
            return 204, ""

        result = post_webhook(
            "https://discord.com/api/webhooks/1/test",
            {"content": "hello"},
            transport=ok,
            max_attempts=1,
        )
        self.assertEqual(result["status"], "SENT")
        self.assertFalse(result["changed_decision"])

    def test_11_protected_hashes_phase16a_unchanged(self):
        protected = verify_protected_hashes()
        self.assertTrue(protected["all_ok"], msg=str(protected))

    def test_12_dry_run_does_not_call_transport(self):
        called = {"n": 0}

        def boom(url, body, timeout):
            called["n"] += 1
            return 200, ""

        with tempfile.TemporaryDirectory() as tmp:
            notifier = DiscordNotifier(
                ledger=DeliveryLedger(Path(tmp) / "l.jsonl"),
                dry_run=True,
                env={"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/test"},
                transport=boom,
            )
            result = notifier.notify(
                decision_to_event(
                    {
                        "decision_id": "dry1",
                        "experimental_action": "WAIT",
                        "final_action": "WAIT",
                    }
                )
            )
            self.assertEqual(result["status"], "DRY_RUN")
            self.assertEqual(called["n"], 0)

    def test_13_wait_formatter_helper(self):
        payload = format_wait({"event_id": "e1", "decision_id": "e1", "decision_reason": "r"})
        self.assertIn("WAIT", payload["content"])


if __name__ == "__main__":
    unittest.main()
