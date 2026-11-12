"""Normalized XAUUSD/XAUUSDm weekly schedule with DST seasons (UTC source)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from phase64_12.constants import (
    ACTIVE_SYMBOL,
    BASE_INSTRUMENT,
    BREAK,
    BROKER_PUBLISHED_SESSION,
    CLOSED,
    DST_WINTER_EFFECTIVE,
    NEXT_US_DST_START,
    OPEN,
    RETRIEVAL_DATE,
    SCHEDULE_VERSION,
    SERVER_TZ,
    SRC_DST_UPDATE,
    SRC_MT_TIMEZONE,
    SRC_TRADING_HOURS,
    UNKNOWN,
    USER_TZ,
    canonical_json_sha256,
)

UTC = ZoneInfo("UTC")
PKT = ZoneInfo(USER_TZ)

# Segment kinds inside a weekday: (start_inclusive, end_exclusive, state)
# Times are local to published timezone UTC.


def _seg(start: str, end: str, state: str) -> dict[str, str]:
    return {"start": start, "end": end, "state": state}


def _parse_hms(s: str) -> time:
    parts = [int(p) for p in s.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


# Official Exness DST update table for XAUUSD (UTC)
WINTER_WEEKLY: dict[int, list[dict[str, str]]] = {
    # Monday=0 … Sunday=6 (Python weekday)
    0: [  # Mon
        _seg("00:00:00", "21:58:00", OPEN),
        _seg("21:58:00", "23:00:30", CLOSED),
        _seg("23:00:30", "23:02:00", BREAK),  # Close Only → treat as BREAK (reject new orders)
        _seg("23:02:00", "24:00:00", OPEN),
    ],
    1: [  # Tue — same as Mon–Thu
        _seg("00:00:00", "21:58:00", OPEN),
        _seg("21:58:00", "23:00:30", CLOSED),
        _seg("23:00:30", "23:02:00", BREAK),
        _seg("23:02:00", "24:00:00", OPEN),
    ],
    2: [
        _seg("00:00:00", "21:58:00", OPEN),
        _seg("21:58:00", "23:00:30", CLOSED),
        _seg("23:00:30", "23:02:00", BREAK),
        _seg("23:02:00", "24:00:00", OPEN),
    ],
    3: [
        _seg("00:00:00", "21:58:00", OPEN),
        _seg("21:58:00", "23:00:30", CLOSED),
        _seg("23:00:30", "23:02:00", BREAK),
        _seg("23:02:00", "24:00:00", OPEN),
    ],
    4: [  # Fri
        _seg("00:00:00", "21:58:00", OPEN),
        _seg("21:58:00", "24:00:00", CLOSED),
    ],
    5: [  # Sat
        _seg("00:00:00", "24:00:00", CLOSED),
    ],
    6: [  # Sun
        _seg("00:00:00", "23:01:30", CLOSED),
        _seg("23:01:30", "23:05:00", BREAK),
        _seg("23:05:00", "24:00:00", OPEN),
    ],
}

SUMMER_WEEKLY: dict[int, list[dict[str, str]]] = {
    0: [
        _seg("00:00:00", "20:58:00", OPEN),
        _seg("20:58:00", "22:00:30", CLOSED),
        _seg("22:00:30", "22:02:00", BREAK),
        _seg("22:02:00", "24:00:00", OPEN),
    ],
    1: [
        _seg("00:00:00", "20:58:00", OPEN),
        _seg("20:58:00", "22:00:30", CLOSED),
        _seg("22:00:30", "22:02:00", BREAK),
        _seg("22:02:00", "24:00:00", OPEN),
    ],
    2: [
        _seg("00:00:00", "20:58:00", OPEN),
        _seg("20:58:00", "22:00:30", CLOSED),
        _seg("22:00:30", "22:02:00", BREAK),
        _seg("22:02:00", "24:00:00", OPEN),
    ],
    3: [
        _seg("00:00:00", "20:58:00", OPEN),
        _seg("20:58:00", "22:00:30", CLOSED),
        _seg("22:00:30", "22:02:00", BREAK),
        _seg("22:02:00", "24:00:00", OPEN),
    ],
    4: [
        _seg("00:00:00", "20:58:00", OPEN),
        _seg("20:58:00", "24:00:00", CLOSED),
    ],
    5: [
        _seg("00:00:00", "24:00:00", CLOSED),
    ],
    6: [
        _seg("00:00:00", "22:01:30", CLOSED),
        _seg("22:01:30", "22:05:00", BREAK),
        _seg("22:05:00", "24:00:00", OPEN),
    ],
}

# Holidays that may affect hours — instrument-specific amendments not published here
HOLIDAYS_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 11),
        date(2026, 11, 26),
        date(2026, 12, 25),
        date(2026, 12, 28),
        date(2026, 12, 31),
        date(2027, 1, 1),
    }
)


def us_dst_season(d: date) -> str:
    """
    US DST: summer from second Sunday in March through day before first Sunday in November.
    Server clock remains UTC+0; schedule windows shift with US DST.
    """
    year = d.year
    # second Sunday March
    march1 = date(year, 3, 1)
    first_sun_march = march1 + timedelta(days=(6 - march1.weekday()) % 7)
    second_sun_march = first_sun_march + timedelta(days=7)
    # first Sunday November
    nov1 = date(year, 11, 1)
    first_sun_nov = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    if second_sun_march <= d < first_sun_nov:
        return "SUMMER"
    return "WINTER"


def weekly_for_season(season: str) -> dict[int, list[dict[str, str]]]:
    return SUMMER_WEEKLY if season == "SUMMER" else WINTER_WEEKLY


def _seconds_since_midnight(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _end_seconds(end: str) -> int:
    if end in ("24:00:00", "24:00"):
        return 24 * 3600
    return _seconds_since_midnight(_parse_hms(end))


def state_at_utc(ts: datetime, *, honor_holidays: bool = True) -> dict[str, Any]:
    """Determine OPEN/CLOSED/BREAK/UNKNOWN for a timezone-aware timestamp."""
    if ts.tzinfo is None:
        return {
            "state": UNKNOWN,
            "reason": "naive_datetime_rejected",
            "season": UNKNOWN,
            "fail_closed": True,
        }
    ts_utc = ts.astimezone(UTC)
    d = ts_utc.date()
    if honor_holidays and d in HOLIDAYS_2026:
        return {
            "state": UNKNOWN,
            "reason": "holiday_date_without_instrument_specific_hours",
            "season": us_dst_season(d),
            "utc": ts_utc.isoformat(),
            "pkt": ts_utc.astimezone(PKT).isoformat(),
            "fail_closed": True,
            "holiday": True,
        }
    season = us_dst_season(d)
    weekly = weekly_for_season(season)
    segs = weekly[ts_utc.weekday()]
    sec = _seconds_since_midnight(ts_utc.timetz().replace(tzinfo=None))
    for seg in segs:
        start_s = _seconds_since_midnight(_parse_hms(seg["start"]))
        end_s = _end_seconds(seg["end"])
        if start_s <= sec < end_s:
            return {
                "state": seg["state"],
                "reason": "schedule_match",
                "season": season,
                "segment": seg,
                "weekday_utc": ts_utc.weekday(),
                "utc": ts_utc.isoformat(),
                "pkt": ts_utc.astimezone(PKT).isoformat(),
                "fail_closed": seg["state"] != OPEN,
                "holiday": False,
            }
    return {
        "state": UNKNOWN,
        "reason": "no_segment_match",
        "season": season,
        "fail_closed": True,
    }


def pkt_view_of_segments(season: str = "WINTER") -> dict[str, Any]:
    """Convert UTC segments to Asia/Karachi (UTC+5, no DST) for reporting."""
    weekly = weekly_for_season(season)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out_days = {}
    for wd, segs in weekly.items():
        mapped = []
        for seg in segs:
            # Represent as UTC wall + PKT wall for same clock reading on a reference Monday
            # Use a fixed reference date in that season
            ref = date(2026, 11, 9) if season == "WINTER" else date(2026, 7, 6)  # Mon
            # shift to target weekday
            ref = ref + timedelta(days=(wd - ref.weekday()) % 7)
            start_t = _parse_hms(seg["start"])
            end_label = seg["end"]
            start_utc = datetime.combine(ref, start_t, tzinfo=UTC)
            if end_label in ("24:00:00", "24:00"):
                end_utc = datetime.combine(ref + timedelta(days=1), time(0, 0, 0), tzinfo=UTC)
            else:
                end_utc = datetime.combine(ref, _parse_hms(end_label), tzinfo=UTC)
            mapped.append(
                {
                    "state": seg["state"],
                    "utc_start": seg["start"],
                    "utc_end": seg["end"],
                    "pkt_start": start_utc.astimezone(PKT).strftime("%H:%M:%S"),
                    "pkt_end": (
                        "05:00:00(+1d)"
                        if end_label in ("24:00:00", "24:00")
                        else end_utc.astimezone(PKT).strftime("%H:%M:%S")
                    ),
                }
            )
        out_days[day_names[wd]] = mapped
    return {"season": season, "user_tz": USER_TZ, "days": out_days}


def build_verified_schedule_spec() -> dict[str, Any]:
    out = {
        "schedule_version": SCHEDULE_VERSION,
        "symbol": ACTIVE_SYMBOL,
        "published_as": BASE_INSTRUMENT,
        "evidence_kind": BROKER_PUBLISHED_SESSION,
        "source_timezone": SERVER_TZ,
        "server_observes_dst": False,
        "hours_shift_with_us_dst": True,
        "us_dst_rule": "Summer: 2nd Sunday March → day before 1st Sunday November",
        "effective_winter_from": DST_WINTER_EFFECTIVE,
        "next_summer_from": NEXT_US_DST_START,
        "retrieval_date": RETRIEVAL_DATE,
        "source_url": SRC_DST_UPDATE,
        "timezone_source_url": SRC_MT_TIMEZONE,
        "hours_context_url": SRC_TRADING_HOURS,
        "close_only_mapped_to": BREAK,
        "close_only_note": "Close Only is not OPEN for new orders; mapped to BREAK (fail closed)",
        "winter_weekly_utc": {str(k): v for k, v in WINTER_WEEKLY.items()},
        "summer_weekly_utc": {str(k): v for k, v in SUMMER_WEEKLY.items()},
        "pkt_winter": pkt_view_of_segments("WINTER"),
        "pkt_summer": pkt_view_of_segments("SUMMER"),
        "rollover": {
            "summer_utc": "21:00",
            "winter_utc": "22:00",
            "source": SRC_TRADING_HOURS,
            "note": "Gold usually closed during forex rollover; liquidity thinner",
        },
        "holidays": {
            "calendar_year": 2026,
            "instrument_specific_hours": UNKNOWN,
            "policy": "On listed holiday dates without XAUUSD-specific amendment → UNKNOWN fail-closed",
            "dates": sorted(d.isoformat() for d in HOLIDAYS_2026),
        },
        "inferred_from_gaps": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
