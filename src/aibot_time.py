"""Global AIBOT timestamp display standard (UTC / PKT labels).

Storage and calculations keep unlabeled UTC wall-clock or ISO-Z strings.
User-visible surfaces must call these display helpers so every shown stamp
ends with an explicit timezone identity: UTC or PKT (Asia/Karachi, UTC+05:00).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

UTC = timezone.utc
PKT_TZ_NAME = "Asia/Karachi"
PKT = ZoneInfo(PKT_TZ_NAME)
PKT_OFFSET = timedelta(hours=5)

# Naive stamps are only accepted when the caller declares their meaning.
_NAIVE_UTC_OK = frozenset({"utc", "z", "zulu", "coordinated universal time"})


class TimestampDisplayError(ValueError):
    """Raised when a timezone label would be attached to an ambiguous value."""


def ensure_aware_utc(value: datetime | str, *, naive_means: str = "utc") -> datetime:
    """Parse/normalize to timezone-aware UTC. Reject ambiguous naive values."""
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            if str(naive_means).lower() not in _NAIVE_UTC_OK:
                raise TimestampDisplayError(
                    "refusing to label timezone-naive datetime without established timezone"
                )
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    text = str(value).strip()
    if not text:
        raise TimestampDisplayError("empty timestamp")

    # Strip an already-present display label before parsing.
    for suffix in (" (UTC)", " (PKT)", " UTC", " PKT"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()

    if text.endswith("Z"):
        text = text[:-1]
    text = text.replace("T", " ")
    # Drop numeric offset if present on ISO-like strings for wall parse, then re-attach.
    if "+" in text[10:]:
        # e.g. 2026-11-09 18:45:00+05:00 — interpret as offset-aware then convert.
        try:
            iso = str(value).strip()
            for suffix in (" (UTC)", " (PKT)"):
                if iso.endswith(suffix):
                    iso = iso[: -len(suffix)].strip()
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise TimestampDisplayError("ambiguous")
            return dt.astimezone(UTC)
        except Exception as exc:
            raise TimestampDisplayError(f"unparseable offset timestamp: {value}") from exc

    try:
        dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise TimestampDisplayError(f"unparseable timestamp: {value}") from exc
    if str(naive_means).lower() not in _NAIVE_UTC_OK:
        raise TimestampDisplayError(
            "refusing to label timezone-naive stamp without established timezone"
        )
    return dt.replace(tzinfo=UTC)


def display_utc(value: datetime | str, *, naive_means: str = "utc") -> str:
    """`2026-11-09 13:45:00 UTC`"""
    dt = ensure_aware_utc(value, naive_means=naive_means)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + " UTC"


def display_pkt(value: datetime | str, *, naive_means: str = "utc") -> str:
    """`2026-11-09 18:45:00 PKT`"""
    dt = ensure_aware_utc(value, naive_means=naive_means).astimezone(PKT)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + " PKT"


def display_utc_iso(value: datetime | str, *, naive_means: str = "utc") -> str:
    """`2026-11-09T13:45:00Z (UTC)`"""
    dt = ensure_aware_utc(value, naive_means=naive_means)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") + " (UTC)"


def display_pkt_iso(value: datetime | str, *, naive_means: str = "utc") -> str:
    """`2026-11-09T18:45:00+05:00 (PKT)`"""
    dt = ensure_aware_utc(value, naive_means=naive_means).astimezone(PKT)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+05:00") + " (PKT)"


def display_pkt_clock(value: datetime | str, *, naive_means: str = "utc") -> str:
    """`18:45 PKT`"""
    dt = ensure_aware_utc(value, naive_means=naive_means).astimezone(PKT)
    return dt.strftime("%H:%M") + " PKT"


def display_pkt_date(value: datetime | str, *, naive_means: str = "utc") -> str:
    """`2026-11-09 PKT`"""
    dt = ensure_aware_utc(value, naive_means=naive_means).astimezone(PKT)
    return dt.strftime("%Y-%m-%d") + " PKT"


def storage_utc_wall(value: datetime | str, *, naive_means: str = "utc") -> str:
    """Unlabeled UTC wall-clock for storage/calculations only."""
    dt = ensure_aware_utc(value, naive_means=naive_means)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def storage_utc_iso(value: datetime | str, *, naive_means: str = "utc") -> str:
    """Unlabeled ISO-Z for machine JSON fields."""
    dt = ensure_aware_utc(value, naive_means=naive_means)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_to_pkt_offset_ok(value: datetime | str, *, naive_means: str = "utc") -> bool:
    """True when PKT wall clock is exactly UTC + 05:00 for this instant."""
    utc_dt = ensure_aware_utc(value, naive_means=naive_means)
    pkt_dt = utc_dt.astimezone(PKT)
    # Compare naive wall components after applying fixed +5h (PKT has no DST).
    shifted = (utc_dt + PKT_OFFSET).replace(tzinfo=None)
    return shifted.strftime("%Y-%m-%d %H:%M:%S") == pkt_dt.replace(tzinfo=None).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def assert_labeled(text: str) -> None:
    """Assert a display string carries an explicit UTC or PKT identity."""
    s = str(text).strip()
    if s.endswith(" UTC") or s.endswith("PKT") or s.endswith("(UTC)") or s.endswith("(PKT)"):
        return
    raise AssertionError(f"timestamp display missing UTC/PKT label: {text!r}")


def dual_display(value: datetime | str, *, naive_means: str = "utc") -> dict[str, str]:
    """Common pair for reports that show both zones."""
    return {
        "utc": display_utc(value, naive_means=naive_means),
        "pkt": display_pkt(value, naive_means=naive_means),
        "utc_iso": display_utc_iso(value, naive_means=naive_means),
        "pkt_iso": display_pkt_iso(value, naive_means=naive_means),
        "storage_utc": storage_utc_wall(value, naive_means=naive_means),
    }


def maybe_display_utc(value: Any) -> str:
    """Best-effort labeled UTC for templates; empty input stays empty."""
    if value in (None, ""):
        return ""
    return display_utc(value)


def maybe_display_pkt(value: Any) -> str:
    if value in (None, ""):
        return ""
    return display_pkt(value)


def maybe_display_pkt_clock(value: Any) -> str:
    if value in (None, ""):
        return ""
    return display_pkt_clock(value)
