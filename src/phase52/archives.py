"""Reuse existing XAUUSD archives before any new retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase52.constants import PHASE43_M5, PHASE43_TICKS, PHASE49_M5, PHASE49_TICKS, PHASE51_M5, PHASE51_TICKS


def _list_days(m5_dir: Path, symbol: str) -> list[str]:
    if not m5_dir.is_dir():
        return []
    days = []
    for p in m5_dir.glob(f"m5_{symbol}_*.jsonl"):
        # m5_XAUUSD_YYYY-MM-DD.jsonl
        name = p.stem
        day = name.split("_")[-1]
        if len(day) == 10 and day[4] == "-":
            days.append(day)
    return sorted(set(days))


def _tick_hours_for_day(tick_dir: Path, symbol: str, day: str) -> int:
    if not tick_dir.is_dir():
        return 0
    return sum(1 for h in range(24) if (tick_dir / f"ticks_{symbol}_{day}_{h:02d}h.jsonl").is_file())


def _sample_spreads_from_ticks(tick_dir: Path, symbol: str, day: str, max_files: int = 6) -> list[float]:
    spreads: list[float] = []
    n_files = 0
    for h in range(24):
        path = tick_dir / f"ticks_{symbol}_{day}_{h:02d}h.jsonl"
        if not path.is_file():
            continue
        n_files += 1
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            if t.get("bid") is None or t.get("ask") is None:
                continue
            bid, ask = float(t["bid"]), float(t["ask"])
            if ask >= bid:
                spreads.append(ask - bid)
        if n_files >= max_files:
            break
    return spreads


def inventory_xauusd_archives() -> dict[str, Any]:
    symbol = "XAUUSD"
    out = {"symbol": symbol, "sources": {}}
    for label, m5_dir, tick_dir in (
        ("phase43", PHASE43_M5, PHASE43_TICKS),
        ("phase49", PHASE49_M5, PHASE49_TICKS),
        ("phase51", PHASE51_M5, PHASE51_TICKS),
    ):
        days = _list_days(m5_dir, symbol)
        tick_complete = 0
        sample_day = days[len(days) // 2] if days else None
        spreads = []
        if sample_day:
            tick_complete = sum(1 for d in days if _tick_hours_for_day(tick_dir, symbol, d) >= 20)
            spreads = _sample_spreads_from_ticks(tick_dir, symbol, sample_day)
        out["sources"][label] = {
            "m5_days": len(days),
            "day_span": [days[0], days[-1]] if days else None,
            "days_with_ge20_tick_hours": tick_complete,
            "sample_day": sample_day,
            "sample_spreads_n": len(spreads),
            "sample_spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
            "sample_spread_median": _median(spreads),
            "sample_spread_p95": _pct(spreads, 0.95),
            "archive_present": len(days) > 0,
        }
    # Combined unique days across archives
    all_days = set()
    for label, m5_dir, _ in (
        ("phase43", PHASE43_M5, PHASE43_TICKS),
        ("phase49", PHASE49_M5, PHASE49_TICKS),
        ("phase51", PHASE51_M5, PHASE51_TICKS),
    ):
        all_days |= set(_list_days(m5_dir, symbol))
    out["combined_unique_m5_days"] = len(all_days)
    out["combined_span"] = [min(all_days), max(all_days)] if all_days else None
    return out


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    return ys[mid] if n % 2 else 0.5 * (ys[mid - 1] + ys[mid])


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(p * (len(ys) - 1))))
    return ys[i]
