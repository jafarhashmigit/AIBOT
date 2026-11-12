"""Read-only Phase43 archives with Phase44 validation date hard gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase46.constants import (
    ENGINEERING_DATES,
    FORBIDDEN_VALIDATION_DATES,
    PHASE43_RAW_M5,
    PHASE43_RAW_TICKS,
    SYMBOL,
)


class ForbiddenDateError(RuntimeError):
    pass


def assert_date_allowed(day: str) -> None:
    if day in FORBIDDEN_VALIDATION_DATES:
        raise ForbiddenDateError(
            f"Phase44 validation date forbidden for Phase46: {day}"
        )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_m5(day: str) -> list[dict[str, Any]]:
    assert_date_allowed(day)
    rows = load_jsonl(PHASE43_RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_ticks(day: str) -> list[dict[str, Any]]:
    assert_date_allowed(day)
    ticks: list[dict[str, Any]] = []
    for h in range(24):
        ticks.extend(load_jsonl(PHASE43_RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"))
    ticks.sort(key=lambda t: int(t["timestamp_msc"]))
    return ticks


def ticks_by_m5_bar(ticks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for t in ticks:
        if t.get("bid") is None or t.get("ask") is None:
            continue
        bid, ask = float(t["bid"]), float(t["ask"])
        if ask < bid:
            continue
        ts = str(t["timestamp_utc"])
        # "YYYY-MM-DD HH:MM:SS.mmm"
        minute = int(ts[14:16])
        floored = minute - (minute % 5)
        bar_t = f"{ts[:14]}{floored:02d}:00"
        by.setdefault(bar_t, []).append(
            {
                "epoch_ms": int(t["timestamp_msc"]),
                "timestamp_utc": ts,
                "bid": bid,
                "ask": ask,
            }
        )
    for k in by:
        by[k].sort(key=lambda x: int(x["epoch_ms"]))
    return by


def engineering_dates_present() -> list[str]:
    out = []
    for d in ENGINEERING_DATES:
        assert_date_allowed(d)
        p = PHASE43_RAW_M5 / f"m5_{SYMBOL}_{d}.jsonl"
        if p.is_file():
            out.append(d)
    return out


def verify_no_forbidden_access(accessed_dates: list[str]) -> dict[str, Any]:
    bad = sorted(set(accessed_dates) & FORBIDDEN_VALIDATION_DATES)
    return {
        "ok": len(bad) == 0,
        "accessed_dates": sorted(set(accessed_dates)),
        "forbidden_hits": bad,
    }
