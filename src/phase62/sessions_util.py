"""Lightweight session label for accumulation coverage — heuristic only."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
PKT = ZoneInfo("Asia/Karachi")


def session_label(ts: str) -> str:
    try:
        dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        h = dt.astimezone(PKT).hour
    except Exception:
        return "UNKNOWN"
    if 17 <= h <= 23 or h <= 1:
        return "NY"
    if 12 <= h < 17:
        return "LONDON"
    if 5 <= h < 12:
        return "ASIA"
    return "OFF_HOURS"
