"""Concise Phase 29 Discord payloads (notification-only)."""

from __future__ import annotations

from typing import Any

from aibot_time import display_pkt_clock, ensure_aware_utc
from phase29.constants import STRATEGY_ID, SYMBOL
from phase29.levels import format_price


def _clock_pair(close_utc: str) -> str:
    """`13:40 UTC | 18:40 PKT` from candle close / decision time."""
    dt = ensure_aware_utc(close_utc)
    utc_hm = dt.strftime("%H:%M") + " UTC"
    pkt_hm = display_pkt_clock(dt)
    return f"{utc_hm} | {pkt_hm}"


def build_buy_payload(decision: dict[str, Any]) -> dict[str, str]:
    entry = float(decision["entry"])
    tp = float(decision["tp_level"])
    sl = float(decision["sl_level"])
    close_utc = decision["decision_timestamp_utc"]
    content = "\n".join(
        [
            "**AIBOT — BUY 🟢**",
            "",
            f"{SYMBOL} • {STRATEGY_ID}",
            f"Entry: **{format_price(entry)}**",
            f"TP: **{format_price(tp)}**",
            f"SL: **{format_price(sl)}**",
            _clock_pair(close_utc),
            f"`{decision['decision_id']}`",
        ]
    )
    return {"content": content}


def build_sell_payload(decision: dict[str, Any]) -> dict[str, str]:
    entry = float(decision["entry"])
    tp = float(decision["tp_level"])
    sl = float(decision["sl_level"])
    close_utc = decision["decision_timestamp_utc"]
    content = "\n".join(
        [
            "**AIBOT — SELL 🔴**",
            "",
            f"{SYMBOL} • {STRATEGY_ID}",
            f"Entry: **{format_price(entry)}**",
            f"TP: **{format_price(tp)}**",
            f"SL: **{format_price(sl)}**",
            _clock_pair(close_utc),
            f"`{decision['decision_id']}`",
        ]
    )
    return {"content": content}


def build_wait_payload(decision: dict[str, Any]) -> dict[str, str]:
    close_utc = decision["decision_timestamp_utc"]
    content = "\n".join(
        [
            "**AIBOT — WAIT ⏸️**",
            "",
            f"{SYMBOL} • {STRATEGY_ID}",
            _clock_pair(close_utc),
            f"`{decision['decision_id']}`",
        ]
    )
    return {"content": content}


def build_signal_payload(decision: dict[str, Any]) -> dict[str, str]:
    action = str(decision.get("experimental_action", "WAIT")).upper()
    if action == "BUY":
        return build_buy_payload(decision)
    if action == "SELL":
        return build_sell_payload(decision)
    if action == "WAIT":
        return build_wait_payload(decision)
    raise ValueError(f"unsupported experimental_action: {action}")


def assert_concise_payload(content: str) -> None:
    """Guard against leaking verbose fields into Discord bodies."""
    forbidden = (
        "Champion",
        "Production Action",
        "event_id",
        "candle_close_utc",
        "Notification only",
        "NO_MODEL",
        "EXPERIMENTAL",
    )
    for phrase in forbidden:
        if phrase in content:
            raise ValueError(f"forbidden Discord field present: {phrase}")
    # Must show both zones on the clock line.
    if " UTC" not in content or "PKT" not in content:
        raise ValueError("Discord payload missing UTC/PKT labels")
    # Full wall stamps like "2026-11-09 13:45:00 UTC" are ok via display helpers,
    # but the required format uses HH:MM UTC | HH:MM PKT.
    if " | " not in content:
        raise ValueError("Discord payload missing UTC|PKT clock pair")
