"""Read-only loader for approved archived M5/H1/ticks (no Phase0–53 mutation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase54.constants import PHASE44_VALIDATION, PHASE49_CONFIRMATION, SYMBOL


class ForbiddenArchiveDateError(RuntimeError):
    pass


def sealed_forbidden() -> set[str]:
    forbidden = set(PHASE44_VALIDATION)
    if PHASE49_CONFIRMATION.is_file():
        p49 = json.loads(PHASE49_CONFIRMATION.read_text(encoding="utf-8"))
        forbidden |= set(p49.get("confirmation_dates") or [])
    return forbidden


def assert_day_allowed(day: str) -> None:
    if day in sealed_forbidden():
        raise ForbiddenArchiveDateError(day)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_m5(archive_root: Path, day: str) -> list[dict[str, Any]]:
    assert_day_allowed(day)
    rows = _load_jsonl(archive_root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_h1(archive_root: Path, day: str) -> list[dict[str, Any]]:
    assert_day_allowed(day)
    rows = _load_jsonl(archive_root / "h1" / f"h1_{SYMBOL}_{day}_warmup.jsonl")
    rows.sort(key=lambda r: str(r["timestamp_utc"]))
    return rows


def load_ticks(archive_root: Path, day: str) -> list[dict[str, Any]]:
    assert_day_allowed(day)
    ticks: list[dict[str, Any]] = []
    tick_root = archive_root / "ticks"
    for h in range(24):
        ticks.extend(_load_jsonl(tick_root / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"))
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


def list_archived_m5_days(archive_root: Path) -> list[str]:
    m5 = archive_root / "m5"
    if not m5.is_dir():
        return []
    days = []
    for p in sorted(m5.glob(f"m5_{SYMBOL}_*.jsonl")):
        day = p.stem.replace(f"m5_{SYMBOL}_", "")
        if day in sealed_forbidden():
            continue
        days.append(day)
    return days
