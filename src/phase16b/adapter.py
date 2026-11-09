"""Notification adapter: decision journal → Discord. No decision authority."""

from __future__ import annotations

from typing import Any

from phase16b.client import post_webhook
from phase16b.constants import CHAMPION_STATUS, EXPERIMENTAL_DISCLAIMER
from phase16b.dedupe import DeliveryLedger
from phase16b.formatter import build_payload, resolve_message_type
from phase16b.secrets import load_webhook_url, redact_secrets, safe_config_status, webhook_configured


class DiscordNotifier:
    """Delivers notifications only. Failures never mutate AIBOT decisions."""

    def __init__(
        self,
        *,
        ledger: DeliveryLedger | None = None,
        dry_run: bool = True,
        env: dict[str, str] | None = None,
        transport=None,
    ) -> None:
        self.ledger = ledger or DeliveryLedger()
        self.dry_run = bool(dry_run)
        self.env = env
        self.transport = transport

    def notify(self, event: dict[str, Any]) -> dict[str, Any]:
        event = dict(event)
        event["message_type"] = resolve_message_type(event)
        event.setdefault("champion_status", CHAMPION_STATUS)

        # Never fabricate production BUY/SELL under NO_MODEL
        if event.get("champion_status") == "NO_MODEL":
            if event.get("final_action") in {"BUY", "SELL"}:
                return {
                    "status": "REJECTED_POLICY",
                    "attempts": 0,
                    "error": "no_model_forbids_production_buy_sell_notification_as_live",
                    "changed_decision": False,
                    "message_type": event["message_type"],
                    "dry_run": self.dry_run,
                }

        try:
            key_exists = self.ledger.already_sent(event)
        except ValueError as exc:
            return {
                "status": "REJECTED_INVALID",
                "attempts": 0,
                "error": str(exc),
                "changed_decision": False,
                "dry_run": self.dry_run,
            }
        if key_exists:
            return {
                "status": "SKIPPED_DUPLICATE",
                "attempts": 0,
                "error": None,
                "changed_decision": False,
                "dedupe_key": self.ledger.dedupe_key(event),
                "dry_run": self.dry_run,
            }

        payload = build_payload(event)
        if event["message_type"] in {"EXPERIMENTAL_BUY", "EXPERIMENTAL_SELL"}:
            assert EXPERIMENTAL_DISCLAIMER in payload["content"]

        if not webhook_configured(env=self.env):
            result = {
                "status": "FAILED_CONFIG",
                "attempts": 0,
                "http_status": None,
                "error": "DISCORD_WEBHOOK_URL_not_configured",
                "changed_decision": False,
                "message_type": event["message_type"],
                "dry_run": self.dry_run,
                "config": safe_config_status(env=self.env),
            }
            self.ledger.record(event, result)
            return result

        if self.dry_run:
            result = {
                "status": "DRY_RUN",
                "attempts": 0,
                "http_status": None,
                "error": None,
                "changed_decision": False,
                "message_type": event["message_type"],
                "payload_preview_redacted": redact_secrets(payload["content"][:500]),
                "dry_run": True,
                "config": safe_config_status(env=self.env),
            }
            # Dry-run does not mark as SENT (allows later real send)
            self.ledger.record(event, result)
            return result

        url = load_webhook_url(env=self.env)
        assert url is not None
        result = post_webhook(url, payload, transport=self.transport)
        result["message_type"] = event["message_type"]
        result["dry_run"] = False
        result["changed_decision"] = False
        # Ensure no secret leakage if transport echoed URL somehow
        if result.get("error"):
            result["error"] = redact_secrets(str(result["error"]))
        self.ledger.record(event, result)
        return result


def decision_to_event(decision: dict[str, Any]) -> dict[str, Any]:
    """Map a shadow decision journal row to a notification event."""
    decision_id = decision.get("decision_id") or decision.get("event_id")
    return {
        "event_id": decision_id,
        "decision_id": decision_id,
        "symbol": decision.get("symbol", "XAUUSD"),
        "timeframe": decision.get("timeframe", "M5"),
        "decision_timestamp_utc": decision.get("decision_timestamp_utc", ""),
        "experimental_action": decision.get("experimental_action", decision.get("raw_action", "WAIT")),
        "final_action": decision.get("final_action", "WAIT"),
        "risk_gate_result": decision.get("risk_gate_result", ""),
        "decision_reason": decision.get("decision_reason", ""),
        "champion_status": decision.get("model_status") or decision.get("champion_status") or CHAMPION_STATUS,
        "candidate_status": decision.get("candidate_status", "EXPERIMENTAL"),
    }
