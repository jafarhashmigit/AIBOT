"""UTC internal / PKT user-facing timestamps — wraps aibot_time."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aibot_time import display_pkt, display_utc, ensure_aware_utc

UTC = timezone.utc


def now_utc_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc_iso(value: datetime | str) -> str:
    dt = ensure_aware_utc(value, naive_means="utc")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def dual_stamp(value: datetime | str) -> dict[str, str]:
    return {
        "utc": display_utc(value, naive_means="utc"),
        "pkt": display_pkt(value, naive_means="utc"),
        "iso_z": to_utc_iso(value),
    }


def stamp_fields(prefix: str, value: datetime | str) -> dict[str, Any]:
    d = dual_stamp(value)
    return {
        f"{prefix}_utc": d["utc"],
        f"{prefix}_pkt": d["pkt"],
        f"{prefix}_iso": d["iso_z"],
    }
