"""Deterministic market-data quality validation — no silent repair."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase66.constants import ACTIVE_SYMBOL, MAX_SPREAD_POINTS, MAX_STALE_SEC, MIN_PRICE, SUPERSEDED_SYMBOL


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


def validate_quote(
    *,
    symbol: str,
    bid: float | None,
    ask: float | None,
    server_time_utc: str | None,
    collection_time_utc: str,
    tick_size: float = 0.001,
) -> dict[str, Any]:
    reasons: list[str] = []
    if symbol == SUPERSEDED_SYMBOL:
        reasons.append("superseded_symbol")
    if symbol != ACTIVE_SYMBOL:
        reasons.append("unexpected_symbol")
    if bid is None or ask is None:
        reasons.append("missing_bid_ask")
    else:
        if bid <= 0 or ask <= 0:
            reasons.append("non_positive_price")
        if bid < MIN_PRICE or ask < MIN_PRICE:
            reasons.append("price_below_min_guard")
        if bid > ask:
            reasons.append("bid_greater_than_ask")
        spread = ask - bid
        if spread < 0:
            reasons.append("invalid_spread")
        points = spread / tick_size if tick_size else None
        if points is not None and points > MAX_SPREAD_POINTS:
            reasons.append("abnormal_spread")
    srv = _parse_utc(server_time_utc)
    col = _parse_utc(collection_time_utc)
    if srv is None:
        reasons.append("invalid_timestamp")
    else:
        if col and srv > col:
            # allow small clock skew; large future = reject
            if (srv - col).total_seconds() > 5:
                reasons.append("future_timestamp")
        if col:
            lag = (col - srv).total_seconds()
            if lag > MAX_STALE_SEC:
                reasons.append("stale_observation")
    status = "OK" if not reasons else "REJECTED"
    return {
        "validation_status": status,
        "rejection_reasons": reasons,
        "stale": "stale_observation" in reasons,
        "missing": "missing_bid_ask" in reasons,
        "delayed": False,
        "market_closed_not_failure": False,
    }


def validate_m5_bar(bar: dict[str, Any], *, symbol: str = ACTIVE_SYMBOL) -> dict[str, Any]:
    reasons: list[str] = []
    if symbol != ACTIVE_SYMBOL:
        reasons.append("unexpected_symbol")
    o, h, l, c = bar.get("open"), bar.get("high"), bar.get("low"), bar.get("close")
    if None in (o, h, l, c):
        reasons.append("incomplete_candle")
    else:
        if not (l <= o <= h and l <= c <= h):
            reasons.append("ohlc_inconsistent")
        if min(o, h, l, c) <= 0:
            reasons.append("non_positive_price")
    if not bar.get("timestamp_utc") and not bar.get("time"):
        reasons.append("invalid_timestamp")
    return {
        "validation_status": "OK" if not reasons else "REJECTED",
        "rejection_reasons": reasons,
    }


def classify_unavailability(*, session_state: str, connected: bool) -> str:
    if not connected:
        return "UNAVAILABLE_CONNECTION_FAILURE"
    if session_state in ("CLOSED", "BREAK"):
        return "UNAVAILABLE_MARKET_CLOSED_OR_BREAK"
    if session_state == "UNKNOWN":
        return "UNAVAILABLE_SESSION_UNKNOWN"
    return "AVAILABLE"
