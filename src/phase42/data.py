"""Load Phase40 archives read-only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase42.constants import (
    ALL_DATES,
    PHASE40_RAW_H1,
    PHASE40_RAW_M5,
    PHASE40_RAW_TICKS,
    SYMBOL,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load_m5(day: str) -> list[dict[str, Any]]:
    return load_jsonl(PHASE40_RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl")


def load_h1(day: str) -> list[dict[str, Any]]:
    return load_jsonl(PHASE40_RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl")


def load_ticks_hours(day: str, hours: range | list[int] | None = None) -> list[dict[str, Any]]:
    hours = list(hours) if hours is not None else list(range(24))
    ticks: list[dict[str, Any]] = []
    for h in hours:
        ticks.extend(load_jsonl(PHASE40_RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"))
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
        ts = t["timestamp_utc"]
        minute = int(ts[14:16])
        floored = minute - (minute % 5)
        bar_t = f"{ts[:14]}{floored:02d}:00"
        by.setdefault(bar_t, []).append(
            {"epoch_ms": int(t["timestamp_msc"]), "timestamp_utc": ts, "bid": bid, "ask": ask}
        )
    return by


def list_days() -> list[str]:
    return list(ALL_DATES)
