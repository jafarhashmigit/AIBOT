"""Discord payload formatting. No network I/O. No secret inclusion."""

from __future__ import annotations

from typing import Any

from aibot_time import maybe_display_pkt, maybe_display_utc
from phase16b.constants import (
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    DISCORD_CHANNEL_ID,
    DISCORD_SERVER_ID,
    EXPERIMENTAL_DISCLAIMER,
)


def _base_fields(event: dict[str, Any]) -> list[str]:
    raw = event.get("decision_timestamp_utc", "")
    lines = [
        f"event_id: {event.get('event_id', '')}",
        f"decision_id: {event.get('decision_id', '')}",
        f"symbol: {event.get('symbol', 'XAUUSD')}",
        f"timeframe: {event.get('timeframe', 'M5')}",
        f"decision_timestamp: {maybe_display_utc(raw)}",
        f"decision_timestamp_pkt: {maybe_display_pkt(raw)}",
        f"champion: {event.get('champion_status', CHAMPION_STATUS)}",
        f"candidate_status: {event.get('candidate_status', CANDIDATE_STATUS)}",
    ]
    return lines


def format_wait(event: dict[str, Any]) -> dict[str, str]:
    body = "\n".join(
        [
            "**AIBOT — WAIT**",
            "Production/final action: WAIT",
            f"Experimental action: {event.get('experimental_action', 'WAIT')}",
            f"Reason: {event.get('decision_reason', '')}",
            *_base_fields(event),
            "Discord is notification-only; no broker order.",
        ]
    )
    return {"content": body}


def format_experimental_buy(event: dict[str, Any]) -> dict[str, str]:
    body = "\n".join(
        [
            "**AIBOT — EXPERIMENTAL BUY**",
            EXPERIMENTAL_DISCLAIMER,
            f"Experimental action: BUY",
            f"Production/final action (gated): {event.get('final_action', 'WAIT')}",
            f"Risk gate: {event.get('risk_gate_result', '')}",
            f"Reason: {event.get('decision_reason', '')}",
            *_base_fields(event),
            "Discord is notification-only; no broker order.",
        ]
    )
    return {"content": body}


def format_experimental_sell(event: dict[str, Any]) -> dict[str, str]:
    body = "\n".join(
        [
            "**AIBOT — EXPERIMENTAL SELL**",
            EXPERIMENTAL_DISCLAIMER,
            f"Experimental action: SELL",
            f"Production/final action (gated): {event.get('final_action', 'WAIT')}",
            f"Risk gate: {event.get('risk_gate_result', '')}",
            f"Reason: {event.get('decision_reason', '')}",
            *_base_fields(event),
            "Discord is notification-only; no broker order.",
        ]
    )
    return {"content": body}


def format_pilot_status(event: dict[str, Any]) -> dict[str, str]:
    detail = str(event.get("detail", ""))
    header = "**AIBOT — PILOT STATUS**"
    if "AIBOT TEST — NOT A TRADING SIGNAL" in detail or str(event.get("status", "")).upper() == "TEST":
        header = "**AIBOT TEST — NOT A TRADING SIGNAL**"
    body = "\n".join(
        [
            header,
            f"Status: {event.get('status', '')}",
            f"Session: {event.get('session_id', '')}",
            f"Detail: {detail}",
            *_base_fields(event),
            f"Destination server_id={DISCORD_SERVER_ID} channel_id={DISCORD_CHANNEL_ID}",
            "Notification only. No BUY/SELL. No broker order.",
        ]
    )
    return {"content": body}


def format_error_delivery_failure(event: dict[str, Any]) -> dict[str, str]:
    # Never include webhook URL or raw exception text that may contain it.
    detail = str(event.get("detail", "delivery_failed"))
    body = "\n".join(
        [
            "**AIBOT — ERROR / DELIVERY FAILURE**",
            f"Detail: {detail}",
            f"Original event_id: {event.get('failed_event_id', event.get('event_id', ''))}",
            *_base_fields(event),
            "Underlying AIBOT decision unchanged.",
        ]
    )
    return {"content": body}


def resolve_message_type(event: dict[str, Any]) -> str:
    explicit = event.get("message_type")
    if explicit:
        return str(explicit)
    exp = str(event.get("experimental_action", "WAIT")).upper()
    if exp == "BUY":
        return "EXPERIMENTAL_BUY"
    if exp == "SELL":
        return "EXPERIMENTAL_SELL"
    status = str(event.get("status", "")).upper()
    if status in {"PILOT", "PILOT_STATUS"} or event.get("message_type") == "PILOT_STATUS":
        return "PILOT_STATUS"
    return "WAIT"


def build_payload(event: dict[str, Any]) -> dict[str, str]:
    msg_type = resolve_message_type(event)
    if msg_type == "EXPERIMENTAL_BUY":
        payload = format_experimental_buy(event)
    elif msg_type == "EXPERIMENTAL_SELL":
        payload = format_experimental_sell(event)
    elif msg_type == "PILOT_STATUS":
        payload = format_pilot_status(event)
    elif msg_type == "ERROR_DELIVERY_FAILURE":
        payload = format_error_delivery_failure(event)
    else:
        payload = format_wait(event)
    # Hard guarantee: experimental BUY/SELL always carry disclaimer
    if msg_type in {"EXPERIMENTAL_BUY", "EXPERIMENTAL_SELL"}:
        if EXPERIMENTAL_DISCLAIMER not in payload["content"]:
            payload["content"] = EXPERIMENTAL_DISCLAIMER + "\n" + payload["content"]
    return payload
