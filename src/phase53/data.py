"""Load Phase53 archives with sealed-date guards."""

from __future__ import annotations

import json
from typing import Any

from phase53.constants import PHASE49_SELECTION, RAW_H1, RAW_M5, RAW_TICKS, SYMBOL
from phase53.storage import load_jsonl


class ForbiddenDateError(RuntimeError):
    pass


def sealed_forbidden_dates() -> set[str]:
    from phase44.constants import VALIDATION_DATES

    p49 = json.loads(PHASE49_SELECTION.read_text(encoding="utf-8"))
    return set(VALIDATION_DATES) | set(p49.get("confirmation_dates") or [])


def assert_allowed(day: str) -> None:
    if day in sealed_forbidden_dates():
        raise ForbiddenDateError(day)


def load_m5(day: str) -> list[dict[str, Any]]:
    assert_allowed(day)
    rows = load_jsonl(RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_h1(day: str) -> list[dict[str, Any]]:
    assert_allowed(day)
    rows = load_jsonl(RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_ticks(day: str) -> list[dict[str, Any]]:
    assert_allowed(day)
    ticks: list[dict[str, Any]] = []
    for h in range(24):
        ticks.extend(load_jsonl(RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"))
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
        minute = int(ts[14:16])
        floored = minute - (minute % 5)
        bar_t = f"{ts[:14]}{floored:02d}:00"
        by.setdefault(bar_t, []).append(
            {"epoch_ms": int(t["timestamp_msc"]), "timestamp_utc": ts, "bid": bid, "ask": ask}
        )
    for k in by:
        by[k].sort(key=lambda x: int(x["epoch_ms"]))
    return by
