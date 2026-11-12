"""UTC storage stamp helpers."""

from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def assert_utc_storage_stamp(stamp: str) -> bool:
    """Validate a storage stamp parses as naive UTC wall clock (no TZ suffix required)."""
    try:
        datetime.strptime(stamp.split(".")[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"invalid UTC storage stamp: {stamp}") from exc
    return True
