"""Timezone conversion. Never labels an unknown stamp as UTC. No fixed offset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from phase12.validation import TIME_FORMAT, ShadowError

UTC = timezone.utc
ATHENS = ZoneInfo("Europe/Athens")


class TimestampError(ShadowError):
    pass


def parse_naive(stamp: str) -> datetime:
    try:
        return datetime.strptime(str(stamp), TIME_FORMAT)
    except ValueError as exc:
        raise TimestampError(f"unparseable timestamp: {stamp}") from exc


def fmt_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise TimestampError("refusing to label a naive datetime as UTC")
    return dt.astimezone(UTC).strftime(TIME_FORMAT)


def _athens_to_utc(naive: datetime) -> datetime:
    dst = naive.replace(tzinfo=ATHENS, fold=0).astimezone(UTC)
    std = naive.replace(tzinfo=ATHENS, fold=1).astimezone(UTC)
    if dst != std:
        raise TimestampError(f"DST-ambiguous Europe/Athens timestamp: {naive}")
    roundtrip = dst.astimezone(ATHENS).replace(tzinfo=None)
    if roundtrip != naive:
        raise TimestampError(f"DST-nonexistent Europe/Athens timestamp: {naive}")
    return dst


def normalize(
    stamp: str,
    tz_name: str | None,
    *,
    already_utc: bool = False,
) -> dict:
    """Return UTC clock string plus conversion metadata. Rejects unknown TZ."""
    if already_utc:
        tz_name = "UTC"
    if tz_name is None or str(tz_name).strip() == "" or str(tz_name).lower() in {"unknown", "naive"}:
        raise TimestampError("unknown timezone rejected; will not label as UTC")
    name = str(tz_name)
    naive = parse_naive(stamp)
    if name.upper() == "UTC":
        aware = naive.replace(tzinfo=UTC)
        return {
            "utc": fmt_utc(aware),
            "source_stamp": stamp,
            "source_timezone": "UTC",
            "conversion": "already_utc",
        }
    if name in {"Europe/Athens", "EET", "EET/EEST"}:
        aware = _athens_to_utc(naive)
        offset = naive.replace(tzinfo=ATHENS).utcoffset()
        hours = int(offset.total_seconds() // 3600) if offset is not None else None
        return {
            "utc": fmt_utc(aware),
            "source_stamp": stamp,
            "source_timezone": "Europe/Athens",
            "conversion": "europe_athens_iana_dst",
            "utc_offset_hours": hours,
        }
    raise TimestampError(f"unsupported timezone {name}")


def add_minutes_utc(utc_stamp: str, minutes: int) -> str:
    dt = parse_naive(utc_stamp).replace(tzinfo=UTC)
    return fmt_utc(dt + timedelta(minutes=minutes))
