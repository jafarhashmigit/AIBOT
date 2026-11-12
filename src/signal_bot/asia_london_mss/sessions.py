"""DST-aware Asia / London session helpers — closed-bar only."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from signal_bot.asia_london_mss.constants import (
    ASIA_END_HM,
    ASIA_START_HM,
    ASIA_TZ,
    LONDON_END_HM,
    LONDON_START_HM,
    LONDON_TZ,
)


def parse_utc(ts: str) -> datetime:
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _local_hm(dt_utc: datetime, tz_name: str) -> tuple[datetime, int, int, str]:
    local = dt_utc.astimezone(ZoneInfo(tz_name))
    day = local.date().isoformat()
    return local, local.hour, local.minute, day


def in_asia_session(ts_utc: str) -> bool:
    dt = parse_utc(ts_utc)
    local, h, m, _ = _local_hm(dt, ASIA_TZ)
    start = ASIA_START_HM[0] * 60 + ASIA_START_HM[1]
    end = ASIA_END_HM[0] * 60 + ASIA_END_HM[1]
    cur = h * 60 + m
    return start <= cur < end


def in_london_window(ts_utc: str) -> bool:
    dt = parse_utc(ts_utc)
    _, h, m, _ = _local_hm(dt, LONDON_TZ)
    start = LONDON_START_HM[0] * 60 + LONDON_START_HM[1]
    end = LONDON_END_HM[0] * 60 + LONDON_END_HM[1]
    cur = h * 60 + m
    return start <= cur < end


def asia_day_key(ts_utc: str) -> str:
    dt = parse_utc(ts_utc)
    _, _, _, day = _local_hm(dt, ASIA_TZ)
    return day


def london_day_key(ts_utc: str) -> str:
    dt = parse_utc(ts_utc)
    _, _, _, day = _local_hm(dt, LONDON_TZ)
    return day


def asia_session_complete_at(decision_ts_utc: str, asia_day: str) -> bool:
    """True iff decision time is at/after Asia end on that Asia calendar day."""
    dt = parse_utc(decision_ts_utc)
    local = dt.astimezone(ZoneInfo(ASIA_TZ))
    if local.date().isoformat() != asia_day:
        # After Asia day in Tokyo calendar — treat as complete for that asia_day
        return local.date().isoformat() > asia_day
    end_m = ASIA_END_HM[0] * 60 + ASIA_END_HM[1]
    return (local.hour * 60 + local.minute) >= end_m


def build_asia_range(bars: list[dict[str, Any]], asia_day: str) -> dict[str, Any]:
    """Build Asia high/low from closed bars in Asia session for asia_day only."""
    sess = []
    for b in bars:
        ts = str(b.get("timestamp_utc") or "")
        if not ts:
            continue
        if asia_day_key(ts) != asia_day:
            continue
        if not in_asia_session(ts):
            continue
        sess.append(b)
    if not sess:
        return {"ok": False, "reason": "ASIA_NO_BARS", "asia_day": asia_day, "n": 0}
    highs = [float(b["high"]) for b in sess]
    lows = [float(b["low"]) for b in sess]
    return {
        "ok": True,
        "asia_day": asia_day,
        "n": len(sess),
        "high": max(highs),
        "low": min(lows),
        "first_ts": str(sess[0]["timestamp_utc"]),
        "last_ts": str(sess[-1]["timestamp_utc"]),
        "bars": sess,
    }
