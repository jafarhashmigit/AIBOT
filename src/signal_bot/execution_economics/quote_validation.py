"""Quote validation for execution-economics — reject crossed/stale/invalid."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from signal_bot.execution_economics.constants import (
    ACTIVE_SYMBOL,
    MAX_SPREAD_PRICE,
    STALE_QUOTE_MAX_AGE_SEC,
    SUPERSEDED_SYMBOL,
    VERIFIED_POINT,
    VERIFIED_TICK_SIZE,
)


def _parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def validate_quote_record(
    q: dict[str, Any],
    *,
    point: float = VERIFIED_POINT,
    tick_size: float = VERIFIED_TICK_SIZE,
    stale_max_sec: float = STALE_QUOTE_MAX_AGE_SEC,
) -> dict[str, Any]:
    flags: list[str] = []
    symbol = q.get("symbol")
    if symbol == SUPERSEDED_SYMBOL:
        flags.append("superseded_symbol")
    if symbol != ACTIVE_SYMBOL:
        flags.append("unexpected_symbol")

    bid = q.get("bid")
    ask = q.get("ask")
    if bid is None or ask is None:
        flags.append("missing_bid_ask")
        spread_price = None
    else:
        try:
            bid_f = float(bid)
            ask_f = float(ask)
        except (TypeError, ValueError):
            flags.append("non_numeric_bid_ask")
            bid_f = ask_f = None  # type: ignore[assignment]
            spread_price = None
        else:
            if bid_f <= 0 or ask_f <= 0:
                flags.append("non_positive_price")
            if bid_f > ask_f:
                flags.append("crossed_market")
            if bid_f == ask_f:
                flags.append("zero_spread")
            spread_price = ask_f - bid_f
            if spread_price < 0:
                flags.append("negative_spread")
            if spread_price > MAX_SPREAD_PRICE:
                flags.append("abnormal_spread")

    srv = _parse_utc(q.get("server_timestamp_utc"))
    col = _parse_utc(q.get("collection_timestamp_utc"))
    if srv is None:
        flags.append("invalid_server_timestamp")
    if col is None:
        flags.append("invalid_collection_timestamp")
    if srv and col:
        lag = (col - srv).total_seconds()
        if lag > stale_max_sec:
            flags.append("stale_quote")
        if (srv - col).total_seconds() > 5:
            flags.append("future_server_timestamp")

    if q.get("validation_status") not in (None, "OK"):
        flags.append(f"journal_status_{q.get('validation_status')}")

    # Prefer recomputed spread from bid/ask; fall back to stored field
    if spread_price is None and q.get("spread") is not None:
        try:
            spread_price = float(q["spread"])
        except (TypeError, ValueError):
            flags.append("non_numeric_spread_field")

    spread_ticks = (spread_price / tick_size) if spread_price is not None and tick_size else None
    spread_points = (spread_price / point) if spread_price is not None and point else None

    usable = not flags
    return {
        "usable": usable,
        "quality_flags": flags,
        "bid": bid,
        "ask": ask,
        "spread_price": spread_price,
        "spread_ticks": spread_ticks,
        "spread_points": spread_points,
        "point": point,
        "tick_size": tick_size,
    }
