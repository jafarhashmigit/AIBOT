"""Completed M5 candle ingestion guards for Phase 20."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from aibot_time import display_pkt, display_utc, storage_utc_wall
from phase18.horizons import parse_utc

UTC = timezone.utc
BAR_MINUTES = 5


def is_complete_m5_bar(bar: dict[str, Any], *, as_of_utc: str) -> bool:
    """Reject currently forming / incomplete M5 candles.

    A bar is complete only when as_of is strictly after its close timestamp.
    """
    close = bar.get("bar_close_timestamp_utc")
    open_ts = bar.get("bar_open_timestamp_utc")
    if not close or not open_ts:
        return False
    try:
        open_dt = parse_utc(str(open_ts))
        close_dt = parse_utc(str(close))
        as_of = parse_utc(str(as_of_utc))
    except Exception:
        return False
    if close_dt - open_dt != timedelta(minutes=BAR_MINUTES):
        return False
    return as_of > close_dt


def filter_completed_bars(bars: list[dict[str, Any]], *, as_of_utc: str) -> list[dict[str, Any]]:
    return [b for b in bars if is_complete_m5_bar(b, as_of_utc=as_of_utc)]


def enrich_observation_timestamps(bar: dict[str, Any]) -> dict[str, str]:
    """Attach display labels; keep raw UTC storage fields unlabeled."""
    open_utc = str(bar.get("bar_open_timestamp_utc", ""))
    close_utc = str(bar.get("bar_close_timestamp_utc", ""))
    # Storage / ID-compatible raw UTC (unlabeled).
    raw_close = storage_utc_wall(close_utc) if close_utc else ""
    raw_open = storage_utc_wall(open_utc) if open_utc else ""
    return {
        "candle_timestamp_utc": raw_close or close_utc,
        "candle_timestamp_pkt": display_pkt(close_utc) if close_utc else "",
        "bar_open_timestamp_pkt": display_pkt(open_utc) if open_utc else "",
        # Explicit dual display for user-facing journals/reports.
        "candle_timestamp_utc_display": display_utc(close_utc) if close_utc else "",
        "bar_open_timestamp_utc_display": display_utc(open_utc) if open_utc else "",
        "candle_timestamp_storage_utc": raw_close or close_utc,
        "bar_open_timestamp_storage_utc": raw_open or open_utc,
    }


def assert_not_forming(bar: dict[str, Any], *, as_of_utc: str) -> None:
    if not is_complete_m5_bar(bar, as_of_utc=as_of_utc):
        raise ValueError("incomplete/forming M5 candle rejected")
