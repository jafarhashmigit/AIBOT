"""Load Phase51 archives."""

from __future__ import annotations

from typing import Any

from phase51.constants import RAW_H1, RAW_M5, RAW_TICKS, SYMBOL
from phase51.storage import load_jsonl


def load_m5(day: str) -> list[dict[str, Any]]:
    rows = load_jsonl(RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_h1(day: str) -> list[dict[str, Any]]:
    rows = load_jsonl(RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_ticks(day: str) -> list[dict[str, Any]]:
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
