"""Corrected XAUUSDm schedule — CLOSE_ONLY independent of BREAK/CLOSED."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from phase64_13.constants import (
    ACTIVE_SYMBOL,
    BREAK,
    CLOSE_ONLY,
    CLOSED,
    OPEN,
    SCHEDULE_VERSION,
    SERVER_TZ,
    SESSION_SEMANTICS_VERSION,
    UNKNOWN,
    USER_TZ,
    canonical_json_sha256,
)

UTC = ZoneInfo("UTC")
PKT = ZoneInfo(USER_TZ)


def _seg(start: str, end: str, state: str, published_label: str) -> dict[str, str]:
    return {"start": start, "end": end, "state": state, "published_label": published_label}


def _parse_hms(s: str) -> time:
    parts = [int(p) for p in s.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


def _seconds_since_midnight(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _end_seconds(end: str) -> int:
    if end in ("24:00:00", "24:00"):
        return 24 * 3600
    return _seconds_since_midnight(_parse_hms(end))


# Winter (after US DST end 2026-11-01) — Exness XAUUSD UTC table, corrected semantics
WINTER_WEEKLY: dict[int, list[dict[str, str]]] = {
    0: [
        _seg("00:00:00", "21:58:00", OPEN, "Open"),
        _seg("21:58:00", "23:00:30", BREAK, "Closed"),  # intraday pause
        _seg("23:00:30", "23:02:00", CLOSE_ONLY, "Close Only"),
        _seg("23:02:00", "24:00:00", OPEN, "Open"),
    ],
    1: [
        _seg("00:00:00", "21:58:00", OPEN, "Open"),
        _seg("21:58:00", "23:00:30", BREAK, "Closed"),
        _seg("23:00:30", "23:02:00", CLOSE_ONLY, "Close Only"),
        _seg("23:02:00", "24:00:00", OPEN, "Open"),
    ],
    2: [
        _seg("00:00:00", "21:58:00", OPEN, "Open"),
        _seg("21:58:00", "23:00:30", BREAK, "Closed"),
        _seg("23:00:30", "23:02:00", CLOSE_ONLY, "Close Only"),
        _seg("23:02:00", "24:00:00", OPEN, "Open"),
    ],
    3: [
        _seg("00:00:00", "21:58:00", OPEN, "Open"),
        _seg("21:58:00", "23:00:30", BREAK, "Closed"),
        _seg("23:00:30", "23:02:00", CLOSE_ONLY, "Close Only"),
        _seg("23:02:00", "24:00:00", OPEN, "Open"),
    ],
    4: [
        _seg("00:00:00", "21:58:00", OPEN, "Open"),
        _seg("21:58:00", "24:00:00", CLOSED, "Closed"),  # weekly wind-down
    ],
    5: [
        _seg("00:00:00", "24:00:00", CLOSED, "Closed"),
    ],
    6: [
        _seg("00:00:00", "23:01:30", CLOSED, "Closed"),
        _seg("23:01:30", "23:05:00", CLOSE_ONLY, "Close Only"),
        _seg("23:05:00", "24:00:00", OPEN, "Open"),
    ],
}

SUMMER_WEEKLY: dict[int, list[dict[str, str]]] = {
    0: [
        _seg("00:00:00", "20:58:00", OPEN, "Open"),
        _seg("20:58:00", "22:00:30", BREAK, "Closed"),
        _seg("22:00:30", "22:02:00", CLOSE_ONLY, "Close Only"),
        _seg("22:02:00", "24:00:00", OPEN, "Open"),
    ],
    1: [
        _seg("00:00:00", "20:58:00", OPEN, "Open"),
        _seg("20:58:00", "22:00:30", BREAK, "Closed"),
        _seg("22:00:30", "22:02:00", CLOSE_ONLY, "Close Only"),
        _seg("22:02:00", "24:00:00", OPEN, "Open"),
    ],
    2: [
        _seg("00:00:00", "20:58:00", OPEN, "Open"),
        _seg("20:58:00", "22:00:30", BREAK, "Closed"),
        _seg("22:00:30", "22:02:00", CLOSE_ONLY, "Close Only"),
        _seg("22:02:00", "24:00:00", OPEN, "Open"),
    ],
    3: [
        _seg("00:00:00", "20:58:00", OPEN, "Open"),
        _seg("20:58:00", "22:00:30", BREAK, "Closed"),
        _seg("22:00:30", "22:02:00", CLOSE_ONLY, "Close Only"),
        _seg("22:02:00", "24:00:00", OPEN, "Open"),
    ],
    4: [
        _seg("00:00:00", "20:58:00", OPEN, "Open"),
        _seg("20:58:00", "24:00:00", CLOSED, "Closed"),
    ],
    5: [
        _seg("00:00:00", "24:00:00", CLOSED, "Closed"),
    ],
    6: [
        _seg("00:00:00", "22:01:30", CLOSED, "Closed"),
        _seg("22:01:30", "22:05:00", CLOSE_ONLY, "Close Only"),
        _seg("22:05:00", "24:00:00", OPEN, "Open"),
    ],
}

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
    year = d.year
    march1 = date(year, 3, 1)
    first_sun_march = march1 + timedelta(days=(6 - march1.weekday()) % 7)
    second_sun_march = first_sun_march + timedelta(days=7)
    nov1 = date(year, 11, 1)
    first_sun_nov = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    if second_sun_march <= d < first_sun_nov:
        return "SUMMER"
    return "WINTER"


def weekly_for_season(season: str) -> dict[int, list[dict[str, str]]]:
    return SUMMER_WEEKLY if season == "SUMMER" else WINTER_WEEKLY


def state_at_utc(ts: datetime, *, honor_holidays: bool = True) -> dict[str, Any]:
    if ts.tzinfo is None:
        return {"state": UNKNOWN, "reason": "naive_datetime_rejected", "fail_closed": True}
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
    segs = weekly_for_season(season)[ts_utc.weekday()]
    sec = _seconds_since_midnight(ts_utc.timetz().replace(tzinfo=None))
    for seg in segs:
        start_s = _seconds_since_midnight(_parse_hms(seg["start"]))
        end_s = _end_seconds(seg["end"])
        if start_s <= sec < end_s:
            return {
                "state": seg["state"],
                "published_label": seg["published_label"],
                "reason": "schedule_match",
                "season": season,
                "segment": seg,
                "weekday_utc": ts_utc.weekday(),
                "utc": ts_utc.isoformat(),
                "pkt": ts_utc.astimezone(PKT).isoformat(),
                "fail_closed": seg["state"] != OPEN,
                "holiday": False,
            }
    return {"state": UNKNOWN, "reason": "no_segment_match", "season": season, "fail_closed": True}


def boundary_probe(season: str = "WINTER") -> list[dict[str, Any]]:
    """Exact boundary ±1s probes for winter Tue (2026-11-10) or summer Tue (2026-07-14)."""
    if season == "WINTER":
        day = date(2026, 11, 10)  # Tuesday
        marks = [
            ("21:57:59", OPEN),
            ("21:58:00", BREAK),
            ("23:00:29", BREAK),
            ("23:00:30", CLOSE_ONLY),
            ("23:01:59", CLOSE_ONLY),
            ("23:02:00", OPEN),
        ]
    else:
        day = date(2026, 7, 14)
        marks = [
            ("20:57:59", OPEN),
            ("20:58:00", BREAK),
            ("22:00:29", BREAK),
            ("22:00:30", CLOSE_ONLY),
            ("22:01:59", CLOSE_ONLY),
            ("22:02:00", OPEN),
        ]
    out = []
    for hms, expected in marks:
        t = _parse_hms(hms)
        ts = datetime.combine(day, t, tzinfo=UTC)
        got = state_at_utc(ts)["state"]
        out.append(
            {
                "ts_utc": ts.isoformat(),
                "expected": expected,
                "got": got,
                "pass": got == expected,
                "pkt": ts.astimezone(PKT).isoformat(),
            }
        )
    # Friday→Saturday / Sunday reopen
    extras = [
        (datetime(2026, 11, 13, 21, 57, 59, tzinfo=UTC), OPEN),
        (datetime(2026, 11, 13, 21, 58, 0, tzinfo=UTC), CLOSED),
        (datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC), CLOSED),
        (datetime(2026, 11, 15, 23, 1, 29, tzinfo=UTC), CLOSED),
        (datetime(2026, 11, 15, 23, 1, 30, tzinfo=UTC), CLOSE_ONLY),
        (datetime(2026, 11, 15, 23, 4, 59, tzinfo=UTC), CLOSE_ONLY),
        (datetime(2026, 11, 15, 23, 5, 0, tzinfo=UTC), OPEN),
    ]
    for ts, expected in extras:
        got = state_at_utc(ts)["state"]
        out.append(
            {
                "ts_utc": ts.isoformat(),
                "expected": expected,
                "got": got,
                "pass": got == expected,
                "pkt": ts.astimezone(PKT).isoformat(),
            }
        )
    return out


def build_corrected_schedule_spec() -> dict[str, Any]:
    out = {
        "schedule_version": SCHEDULE_VERSION,
        "semantics_version": SESSION_SEMANTICS_VERSION,
        "symbol": ACTIVE_SYMBOL,
        "source_timezone": SERVER_TZ,
        "user_timezone": USER_TZ,
        "close_only_independent": True,
        "close_only_not_collapsed_to_break": True,
        "mapping_rules": {
            "Open": OPEN,
            "Close Only": CLOSE_ONLY,
            "Closed_intraday_weekday_gap": BREAK,
            "Closed_weekend_or_friday_winddown": CLOSED,
        },
        "position_management_limitation": (
            "Official docs establish Close Only intervals but do not fully specify which "
            "position-management operations the broker will accept. Internal monitoring remains "
            "enabled; broker acceptance is NOT guaranteed."
        ),
        "winter_weekly_utc": {str(k): v for k, v in WINTER_WEEKLY.items()},
        "summer_weekly_utc": {str(k): v for k, v in SUMMER_WEEKLY.items()},
        "boundary_probes_winter": boundary_probe("WINTER"),
        "boundary_probes_summer": boundary_probe("SUMMER"),
    }
    out["boundary_probes_pass"] = all(p["pass"] for p in out["boundary_probes_winter"] + out["boundary_probes_summer"])
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
