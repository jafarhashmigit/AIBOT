"""Canonical Discord message templates — no network I/O; no secrets."""

from __future__ import annotations

from typing import Any

from signal_bot.orchestrator.contract import to_pkt


def _fmt_px(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.3f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_rr(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return f"1:{float(v):.1f}"
    except (TypeError, ValueError):
        return str(v)


def format_signal_message(event: dict[str, Any], *, gated: bool = True) -> dict[str, Any]:
    """
    Build Discord content (+ optional embed fields).
    When gated/blocked actionable signals, message must NOT look like a live trade call.
    """
    action = str(event.get("direction") or "WAIT").upper()
    blocked = str(event.get("publication_status") or "") == "BLOCKED" or gated and not event.get(
        "actionable_discord"
    )
    pkt = event.get("display_timestamp_pkt") or to_pkt(event.get("created_utc"))
    expiry_pkt = to_pkt(event.get("expiry_utc"))

    if action == "WAIT" or blocked:
        header = "AIBOT — WAIT / NON-ACTIONABLE"
        lines = [
            f"**{header}**",
            f"Symbol: `{event.get('symbol')}`  Timeframe: `{event.get('timeframe')}`",
            f"Strategy: `{event.get('strategy_id')}` (`{event.get('strategy_version')}`)",
            f"Direction recorded: `{action}`",
            f"Validation: `{event.get('validation_status')}`",
            f"Risk: `{event.get('risk_check_status')}`",
            f"Publication: `{event.get('publication_status')}`",
        ]
        reasons = event.get("publication_block_reasons") or event.get("reason_codes") or []
        if reasons:
            lines.append("Block/reason codes: " + ", ".join(f"`{r}`" for r in reasons[:12]))
        lines += [
            f"Signal ID: `{event.get('signal_id')}`",
            f"Decision ID: `{event.get('decision_id')}`",
            f"Created: {pkt or event.get('created_utc')}",
            "This is **not** a trading recommendation. No broker order.",
        ]
        content = "\n".join(lines)
        return {
            "content": content,
            "embeds": [],
            "message_type": "NON_ACTIONABLE_WAIT",
            "dedupe_key": f"WAIT:{event.get('signal_id')}",
        }

    # Format for future qualified signals only (gate must allow)
    header = f"{event.get('symbol')} — {action}"
    lines = [
        f"**{header}**",
        f"Strategy: `{event.get('strategy_id')}`",
        f"Entry: {_fmt_px(event.get('entry_reference'))} ({event.get('entry_type')})",
        f"Stop Loss: {_fmt_px(event.get('stop_loss'))}",
        f"Take Profit: {_fmt_px(event.get('take_profit'))}",
        f"Risk/Reward: {_fmt_rr(event.get('reward_risk'))}",
        f"Expiry: {expiry_pkt or event.get('expiry_utc') or 'N/A'}",
        f"Invalidation: {event.get('invalidation') or 'N/A'}",
        f"Validation: `{event.get('validation_status')}`",
        f"Risk: `{event.get('risk_check_status')}`",
        f"Signal ID: `{event.get('signal_id')}`",
        f"Created PKT: {pkt}",
        "Discord notification only — broker `order_send` prohibited.",
    ]
    content = "\n".join(lines)
    embed = {
        "title": header,
        "description": content,
        "fields": [
            {"name": "Entry", "value": _fmt_px(event.get("entry_reference")), "inline": True},
            {"name": "SL", "value": _fmt_px(event.get("stop_loss")), "inline": True},
            {"name": "TP", "value": _fmt_px(event.get("take_profit")), "inline": True},
            {"name": "RR", "value": _fmt_rr(event.get("reward_risk")), "inline": True},
            {"name": "Validation", "value": str(event.get("validation_status")), "inline": True},
            {"name": "Risk", "value": str(event.get("risk_check_status")), "inline": True},
        ],
    }
    return {
        "content": content,
        "embeds": [embed],
        "message_type": f"ACTIONABLE_{action}",
        "dedupe_key": f"{action}:{event.get('signal_id')}",
    }


def format_system_status(detail: str, *, signal_id: str | None = None) -> dict[str, Any]:
    """Non-trading system status — must never resemble BUY/SELL advice."""
    body = "\n".join(
        [
            "**AIBOT — SYSTEM STATUS (NOT A TRADING SIGNAL)**",
            f"Detail: {detail}",
            f"Ref: `{signal_id or 'n/a'}`",
            "No BUY/SELL recommendation. No broker order.",
        ]
    )
    return {
        "content": body,
        "embeds": [],
        "message_type": "SYSTEM_STATUS",
        "dedupe_key": f"STATUS:{signal_id or detail[:32]}",
    }


def format_operational_status(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Operational Discord status (Prompt10). Never BUY/SELL/entry/SL/TP/RR/confidence.
    """
    pkt = snapshot.get("pkt_timestamp") or to_pkt(snapshot.get("created_utc"))
    lines = [
        "**AIBOT — OPERATIONAL STATUS (NOT A TRADING SIGNAL)**",
        f"Event: `{snapshot.get('event') or 'STATUS'}`",
        f"MT5: `{snapshot.get('mt5_connection_state')}`",
        f"Collector: `{snapshot.get('collector_status')}`",
        f"Last quote: `{snapshot.get('last_quote_ts')}`",
        f"Last closed M5: `{snapshot.get('last_m5_ts')}`",
        f"Data freshness (sec): `{snapshot.get('data_freshness_sec')}`",
        f"Current decision: `WAIT`",
        f"Reason: `NO_QUALIFIED_STRATEGY`",
        f"Champion: `NO_MODEL`",
        f"PKT: {pkt}",
        "Actionable BUY/SELL: DISABLED. Broker order_send: PROHIBITED.",
    ]
    content = "\n".join(lines)
    dedupe = f"OPS:{snapshot.get('event')}:{snapshot.get('created_utc') or pkt}"
    return {
        "content": content,
        "embeds": [],
        "message_type": "SYSTEM_STATUS",
        "dedupe_key": dedupe,
        "actionable": False,
    }
