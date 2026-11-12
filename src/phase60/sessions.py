"""PKT-aware session classification — heuristic research labels only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from phase60.constants import PKT, SESSION_WINDOWS_PKT, UTC


def parse_ts_utc(ts: str) -> datetime | None:
    try:
        raw = str(ts)[:19]
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=UTC)
    except Exception:
        return None


def to_pkt(dt: datetime) -> datetime:
    return dt.astimezone(PKT)


def session_label_utc_ts(ts: str) -> str:
    """Classify using PKT local hour derived from UTC timestamp."""
    dt = parse_ts_utc(ts)
    if dt is None:
        return "UNKNOWN"
    h = to_pkt(dt).hour
    # NY window may wrap past midnight PKT (17..26 → 17..23 and 0..1)
    if 17 <= h <= 23 or h <= 1:
        return "NY"
    if 12 <= h < 17:
        return "LONDON"
    if 5 <= h < 12:
        return "ASIA"
    if 2 <= h < 5:
        return "OFF_HOURS"
    return "OFF_HOURS"


def session_stats(timestamps: list[str]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for ts in timestamps:
        lab = session_label_utc_ts(ts)
        counts[lab] = counts.get(lab, 0) + 1
    return {
        "counts": counts,
        "method": "PKT_hour_from_UTC_timestamp",
        "tz": "Asia/Karachi",
        "windows_pkt_heuristic": SESSION_WINDOWS_PKT,
        "label_type": "HEURISTIC_NOT_EXCHANGE_OFFICIAL",
    }
