"""Lightweight tick streaming — avoid loading multi-million-tick days into RAM repeatedly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from phase54.constants import SYMBOL


def iter_tick_files(root: Path, day: str) -> Iterator[Path]:
    tick_root = root / "ticks"
    for h in range(24):
        p = tick_root / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"
        if p.is_file():
            yield p


def tick_file_stats(root: Path, day: str, *, sample_per_hour: int = 200) -> dict[str, Any]:
    """Count lines for volume; sample JSON for bid/ask quality (not full parse)."""
    hours = []
    n = 0
    missing_ba = 0
    crossed = 0
    sampled = 0
    for p in iter_tick_files(root, day):
        try:
            hour = int(p.name.split("_")[-1][:2])
        except Exception:
            hour = -1
        hours.append(hour)
        with p.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.strip():
                    n += 1
                if i < sample_per_hour and line.strip():
                    sampled += 1
                    try:
                        t = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if t.get("bid") is None or t.get("ask") is None:
                        missing_ba += 1
                        continue
                    if float(t["ask"]) < float(t["bid"]):
                        crossed += 1
    return {
        "ticks_n": n,
        "tick_hours_present": hours,
        "missing_ba": missing_ba,
        "crossed": crossed,
        "sampled_for_quality": sampled,
    }


def first_spread_by_bar(root: Path, day: str) -> dict[str, float]:
    return scan_day_ticks(root, day)["spreads"]


def scan_day_ticks(root: Path, day: str) -> dict[str, Any]:
    """One pass: tick count, hours, first spread per M5 bar, crossed/missing samples."""
    out: dict[str, float] = {}
    hours: list[int] = []
    n = 0
    missing_ba = 0
    crossed = 0
    for p in iter_tick_files(root, day):
        try:
            hours.append(int(p.name.split("_")[-1][:2]))
        except Exception:
            pass
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n += 1
                try:
                    t = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if t.get("bid") is None or t.get("ask") is None:
                    missing_ba += 1
                    continue
                bid, ask = float(t["bid"]), float(t["ask"])
                if ask < bid:
                    crossed += 1
                    continue
                ts = str(t.get("timestamp_utc") or "")
                if len(ts) < 16:
                    continue
                try:
                    minute = int(ts[14:16])
                    floored = minute - (minute % 5)
                    bar_t = f"{ts[:14]}{floored:02d}:00"
                except Exception:
                    continue
                if bar_t not in out:
                    out[bar_t] = ask - bid
    return {
        "spreads": out,
        "ticks_n": n,
        "tick_hours_present": hours,
        "missing_ba": missing_ba,
        "crossed": crossed,
    }
