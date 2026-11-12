"""Multi-horizon definitions and PKT timing helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from phase18.constants import (
    BAR_MINUTES,
    HORIZON_LABELS,
    HORIZONS,
    PKT_TZ,
    SELECTED_HORIZON_DISPLAY,
    SELECTED_HORIZON_POLICY,
)

UTC = timezone.utc
PKT = ZoneInfo(PKT_TZ)


def parse_utc(stamp: str) -> datetime:
    text = str(stamp).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=UTC)


def format_utc(dt: datetime) -> str:
    """Unlabeled UTC wall-clock for storage/eligibility math. Prefer display_utc for UI."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def format_pkt(dt: datetime) -> str:
    """User-visible PKT stamp — always ends with explicit PKT label."""
    from aibot_time import display_pkt

    return display_pkt(dt)


def format_pkt_clock(dt: datetime) -> str:
    """User-visible PKT clock — always ends with explicit PKT label."""
    from aibot_time import display_pkt_clock

    return display_pkt_clock(dt)


def display_utc(dt: datetime | str) -> str:
    """User-visible UTC stamp — always ends with explicit UTC label."""
    from aibot_time import display_utc as _display_utc

    return _display_utc(dt)


def pkt_calendar_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(PKT).strftime("%Y-%m-%d")


def horizon_minutes(horizon_id: str) -> int:
    return int(HORIZONS[horizon_id]) * BAR_MINUTES


def horizon_label(horizon_id: str) -> str:
    return HORIZON_LABELS[horizon_id]


def expected_outcome_check_utc(decision_close_utc: str, horizon_id: str) -> str:
    """Eligibility wall-clock approx from decision bar close + horizon minutes.

    Actual evaluation still requires M5 candle availability; this is messaging only.
    """
    start = parse_utc(decision_close_utc)
    end = start + timedelta(minutes=horizon_minutes(horizon_id))
    return format_utc(end)


def expected_outcome_check_pkt(decision_close_utc: str, horizon_id: str) -> str:
    start = parse_utc(decision_close_utc)
    end = start + timedelta(minutes=horizon_minutes(horizon_id))
    return format_pkt_clock(end)


def selected_horizon_info() -> dict[str, Any]:
    return {
        "policy": SELECTED_HORIZON_POLICY,
        "selected_horizon": None,
        "selected_horizon_display": SELECTED_HORIZON_DISPLAY,
        "note": (
            "No validated horizon-selection rule is established. "
            "Do not invent a preferred horizon. "
            "Expected Horizon is an evaluation horizon, not a guaranteed time-to-profit."
        ),
    }


def all_horizon_ids() -> list[str]:
    return list(HORIZONS.keys())


def label_to_horizon_id(label: str) -> str | None:
    for hid, lab in HORIZON_LABELS.items():
        if lab == label.upper() or hid == label.upper():
            return hid
    return None
