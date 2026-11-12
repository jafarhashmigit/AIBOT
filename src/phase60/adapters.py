"""Read-only adapters over Phase54/59 interfaces — no prior-phase mutation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase59.constants import ARCHIVE_ROOTS as P59_ARCHIVE_ROOTS
from phase59.inventory import (
    build_inventory,
    load_jsonl,
    phase58_holdout,
    resolve_root_for_day,
)
from phase59.tick_stream import iter_tick_files, scan_day_ticks


def null_policy_ok(expected: str) -> bool:
    return NullPolicy().version == expected


def inventory() -> dict[str, Any]:
    return build_inventory()


def holdout_days() -> list[str]:
    return list(phase58_holdout())


def archive_roots() -> tuple[tuple[str, Path], ...]:
    return P59_ARCHIVE_ROOTS


def root_for_day(day: str) -> Path | None:
    return resolve_root_for_day(day)


def m5_bars(day: str) -> list[dict[str, Any]]:
    root = root_for_day(day)
    if root is None:
        return []
    from phase60.constants import SYMBOL

    return load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")


def stream_tick_scan(day: str) -> dict[str, Any]:
    root = root_for_day(day)
    if root is None:
        return {"ticks_n": 0, "tick_hours_present": [], "spreads": {}, "missing_ba": 0, "crossed": 0}
    return scan_day_ticks(root, day)


def tick_paths(day: str) -> list[Path]:
    root = root_for_day(day)
    if root is None:
        return []
    return list(iter_tick_files(root, day))
