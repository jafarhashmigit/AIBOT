"""Build labeled feature corpus for a date list. Validation outcomes must not be peeked during discovery."""

from __future__ import annotations

from typing import Any

from phase44.data import load_h1, load_m5, load_ticks, ticks_by_m5_bar
from phase44.features import build_feature_rows
from phase44.labels import attach_forward_labels


def _prev_day(day: str) -> str | None:
    from datetime import date, timedelta

    d = date.fromisoformat(day) - timedelta(days=1)
    # walk back over weekend
    for _ in range(4):
        if d.weekday() < 5:
            return d.isoformat()
        d -= timedelta(days=1)
    return d.isoformat()


def _load_prev_day_m5(prev: str | None) -> list[dict[str, Any]]:
    """Prior-day OHLC for level features only. Prefer Phase43; fallback Phase40 raw M5."""
    if not prev:
        return []
    bars = load_m5(prev)
    if bars:
        return bars
    from pathlib import Path

    from phase44.constants import SRC_DIR, SYMBOL
    from phase44.data import load_jsonl

    p40 = SRC_DIR / "data" / "phase40" / "mt5" / "raw" / "m5" / f"m5_{SYMBOL}_{prev}.jsonl"
    return load_jsonl(p40)


def build_day(day: str, *, need_ticks: bool) -> list[dict[str, Any]]:
    bars = load_m5(day)
    h1 = load_h1(day)
    ticks_by = ticks_by_m5_bar(load_ticks(day)) if need_ticks else None
    prev = _prev_day(day)
    prev_bars = _load_prev_day_m5(prev)
    # Prior-day levels are context only; evaluation day remains Phase43 UNSEEN.
    rows = build_feature_rows(bars, h1, ticks_by, prev_day_bars=prev_bars or None)
    return attach_forward_labels(rows)


def build_corpus(dates: list[str], *, need_ticks: bool) -> dict[str, list[dict[str, Any]]]:
    return {day: build_day(day, need_ticks=need_ticks) for day in dates}
