"""Phase 17 Discord shadow message formatting (does not alter Phase 16B formatters)."""

from __future__ import annotations

from typing import Any

from phase17.constants import (
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    EXPERIMENTAL_DISCLAIMER,
    SHADOW_BUY_HEADER,
    SHADOW_SELL_HEADER,
    SHADOW_WAIT_HEADER,
    SYMBOL,
    TIMEFRAME,
)


def build_shadow_payload(decision: dict[str, Any], observation: dict[str, Any]) -> dict[str, str]:
    exp = str(decision.get("experimental_action", "WAIT")).upper()
    final = str(decision.get("final_action", "WAIT")).upper()
    if exp == "BUY":
        header = SHADOW_BUY_HEADER
    elif exp == "SELL":
        header = SHADOW_SELL_HEADER
    else:
        header = SHADOW_WAIT_HEADER

    lines = [
        f"**{header}**",
    ]
    if exp in {"BUY", "SELL"}:
        lines.append(EXPERIMENTAL_DISCLAIMER)
    lines.extend(
        [
            f"symbol: {observation.get('symbol', SYMBOL)}",
            f"timeframe: {observation.get('timeframe', TIMEFRAME)}",
            f"candle_close_utc: {observation.get('bar_close_timestamp_utc', '')}",
            f"experimental_action: {exp}",
            f"final_production_action: {final}",
            f"model_status: {decision.get('model_status', CHAMPION_STATUS)}",
            f"candidate_status: {decision.get('candidate_status', CANDIDATE_STATUS)}",
            f"decision_id: {decision.get('decision_id', '')}",
            f"event_id: {decision.get('decision_id', '')}",
            "Notification only. No broker order.",
        ]
    )
    content = "\n".join(lines)
    if exp in {"BUY", "SELL"} and EXPERIMENTAL_DISCLAIMER not in content:
        content = EXPERIMENTAL_DISCLAIMER + "\n" + content
    return {"content": content}
