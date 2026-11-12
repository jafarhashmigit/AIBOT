"""UTC normalization and DST boundary probes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from phase37.bars import fetch_m5_range
from phase37.constants import DST_PROBE_DATES

UTC = timezone.utc
ATHENS = ZoneInfo("Europe/Athens")


def interpret_rate_epoch(epoch: int) -> dict[str, Any]:
    """Document raw epoch vs UTC vs Athens interpretations."""
    as_utc = datetime.fromtimestamp(epoch, tz=UTC)
    # If broker stamped Athens wall as if UTC epoch (common confusion): treat naive Athens
    as_athens_wall = datetime.fromtimestamp(epoch, tz=UTC).replace(tzinfo=None)
    athens_as_local = as_athens_wall.replace(tzinfo=ATHENS)
    return {
        "raw_epoch": epoch,
        "python_fromtimestamp_utc": as_utc.strftime("%Y-%m-%d %H:%M:%S%z"),
        "if_epoch_were_athens_wall_then_utc": athens_as_local.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S%z"),
        "athens_offset_hours_at_utc_instant": int(as_utc.astimezone(ATHENS).utcoffset().total_seconds() // 3600),
    }


def probe_dst(handle: Any, symbol: str, *, wall_deadline: float) -> dict[str, Any]:
    results = []
    for day in DST_PROBE_DATES:
        start = day
        end = day + timedelta(hours=8)
        m5 = fetch_m5_range(handle, symbol, start, end, wall_deadline=wall_deadline)
        sample = None
        if m5.get("bars"):
            b0 = m5["bars"][0]
            sample = interpret_rate_epoch(int(b0["time_epoch"]))
            sample["bar_time_utc_field"] = b0["time_utc"]
        results.append(
            {
                "probe_day_utc": day.strftime("%Y-%m-%d"),
                "n_bars": m5.get("n"),
                "ok": m5.get("ok"),
                "error": m5.get("error"),
                "first_bar": (m5.get("analysis") or {}).get("first_timestamp_utc"),
                "last_bar": (m5.get("analysis") or {}).get("last_timestamp_utc"),
                "epoch_interpretation_sample": sample,
            }
        )
    return {
        "windows": ["2026-03-29/30 (EU spring DST)", "2026-10-25/26 (EU fall DST)"],
        "probes": results,
        "assumption_used_in_phase37": "MT5 rate/tick epochs are interpreted via datetime.fromtimestamp(..., tz=UTC)",
        "note": "Compare bar spacing across DST days; Phase37 does not silently relabel unknown TZ as UTC.",
    }
