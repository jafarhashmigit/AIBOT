"""Operational Discord status — SYSTEM_STATUS only; never actionable BUY/SELL."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from phase16b.client import post_webhook
from phase16b.secrets import load_webhook_url, redact_secrets, safe_config_status, webhook_configured
from signal_bot.final_delivery.constants import ENV_OPS_STATUS_LIVE, PROMPT09_VERDICT
from signal_bot.orchestrator.contract import to_pkt
from signal_bot.orchestrator.delivery import DeliveryLedger
from signal_bot.orchestrator.formatter import format_operational_status


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_ops_snapshot_from_health(health: dict[str, Any], *, event: str = "STATUS") -> dict[str, Any]:
    ch = health.get("collection_health") or {}
    return {
        "event": event,
        "mt5_connection_state": health.get("mt5_connection_state") or ch.get("mt5_connection"),
        "collector_status": health.get("service_status") or ch.get("collector_status"),
        "last_quote_ts": health.get("last_quote_server_ts")
        or ch.get("last_quote_server_ts")
        or health.get("last_successful_poll_utc"),
        "last_m5_ts": health.get("last_newly_closed_live_m5_bar") or ch.get("last_m5_server_ts"),
        "data_freshness_sec": health.get("data_freshness_sec"),
        "created_utc": _utc(),
        "pkt_timestamp": to_pkt(_utc()),
        "decision": "WAIT",
        "reason": PROMPT09_VERDICT,
    }


def publish_operational_status(
    snapshot: dict[str, Any],
    *,
    ledger: DeliveryLedger | None = None,
    transport: Any | None = None,
    force_shadow: bool = True,
) -> dict[str, Any]:
    """
    Publish ops status.
    Default: SHADOW (local ledger only).
    Live Discord only if AIBOT_DISCORD_OPS_STATUS_LIVE=1 and webhook configured,
    and message remains SYSTEM_STATUS (never BUY/SELL).
    """
    payload = format_operational_status(snapshot)
    assert payload["message_type"] == "SYSTEM_STATUS"
    assert payload.get("actionable") is False
    # Refuse if content looks like a trade alert
    content_l = payload["content"].lower()
    if "entry:" in content_l or "stop loss:" in content_l or "take profit:" in content_l:
        return {"status": "REFUSED_LOOKS_ACTIONABLE", "network_called": False}

    ledger = ledger or DeliveryLedger()
    dedupe = str(payload["dedupe_key"])
    if ledger.already_delivered(dedupe):
        return {"status": "SKIPPED_DUPLICATE", "network_called": False, "dedupe_key": dedupe}

    live_requested = (os.environ.get(ENV_OPS_STATUS_LIVE) or "").strip() == "1"
    want_live = live_requested and not force_shadow

    if not want_live:
        result = {
            "status": "SHADOW_RECORDED",
            "attempts": 0,
            "http_status": None,
            "error": None,
            "ops_live_env": live_requested,
            "webhook_configured": webhook_configured(),
            "config": safe_config_status(),
        }
        ledger.record(
            dedupe_key=dedupe,
            signal_id=f"OPS:{snapshot.get('event')}",
            result=result,
            payload_meta=payload,
        )
        return {
            **result,
            "network_called": False,
            "payload_preview": payload["content"][:800],
            "message_type": "SYSTEM_STATUS",
            "blocker_if_unverified": (
                None
                if webhook_configured() and live_requested
                else f"Set {ENV_OPS_STATUS_LIVE}=1 and configure DISCORD_WEBHOOK_URL for live ops status"
            ),
        }

    url = load_webhook_url()
    if not url:
        result = {
            "status": "FAILED_CONFIG",
            "attempts": 0,
            "http_status": None,
            "error": "missing_webhook",
        }
        ledger.record(
            dedupe_key=dedupe,
            signal_id=f"OPS:{snapshot.get('event')}",
            result=result,
            payload_meta=payload,
        )
        return {**result, "network_called": False, "message_type": "SYSTEM_STATUS"}

    try:
        result = post_webhook(url, {"content": payload["content"]}, transport=transport)
    except Exception as exc:  # noqa: BLE001
        result = {
            "status": "FAILED_HTTP",
            "attempts": 1,
            "http_status": 0,
            "error": redact_secrets(type(exc).__name__),
        }
    if result.get("error"):
        result["error"] = redact_secrets(str(result["error"]))
    # Only claim SENT if Discord confirmed
    if result.get("status") != "SENT":
        result["delivery_confirmed"] = False
    else:
        result["delivery_confirmed"] = True
    ledger.record(
        dedupe_key=dedupe,
        signal_id=f"OPS:{snapshot.get('event')}",
        result=result,
        payload_meta=payload,
    )
    return {
        **result,
        "network_called": True,
        "message_type": "SYSTEM_STATUS",
        "actionable": False,
    }
