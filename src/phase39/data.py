"""Load Phase38 canonical M5/ticks and build eligibility table."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from phase39.constants import (
    PHASE38_RAW_M5,
    PHASE38_RAW_TICKS,
    SYMBOL,
    TICK_WINDOW_END_HOUR,
    TICK_WINDOW_START_HOUR,
)


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def list_phase38_days() -> list[str]:
    days = []
    for p in sorted(PHASE38_RAW_M5.glob(f"m5_{SYMBOL}_*.jsonl")):
        # m5_XAUUSD_YYYY-MM-DD.jsonl
        day = p.stem.replace(f"m5_{SYMBOL}_", "")
        days.append(day)
    return days


def load_day(day: str) -> dict[str, Any]:
    m5_path = PHASE38_RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl"
    tick_path = PHASE38_RAW_TICKS / f"ticks_{SYMBOL}_{day}_{TICK_WINDOW_START_HOUR:02d}h.jsonl"
    bars = load_jsonl(m5_path) if m5_path.is_file() else []
    ticks = load_jsonl(tick_path) if tick_path.is_file() else []
    spreads = [float(t["ask"]) - float(t["bid"]) for t in ticks if t.get("ask") is not None and t.get("bid") is not None]
    tick_start = ticks[0]["timestamp_utc"] if ticks else None
    tick_end = ticks[-1]["timestamp_utc"] if ticks else None
    # missing M5 intervals
    epochs = [int(b["time_epoch"]) for b in bars]
    missing = 0
    for i in range(1, len(epochs)):
        d = epochs[i] - epochs[i - 1]
        if d != 300 and 0 < d < 1800:
            missing += 1
    quality = "OK"
    if not bars:
        quality = "NO_M5"
    elif not ticks:
        quality = "NO_TICKS"
    elif missing:
        quality = "M5_UNEXPECTED_GAPS"

    # ticks by M5 bar open (floor to 5 min)
    ticks_by_bar: dict[str, list[dict]] = {}
    for t in ticks:
        ts = t["timestamp_utc"]
        # floor to M5: YYYY-MM-DD HH:MM where MM in {00,05,...,55}
        minute = int(ts[14:16])
        floored = minute - (minute % 5)
        bar_t = f"{ts[:14]}{floored:02d}:00"
        # normalize epoch_ms
        row = {
            **t,
            "epoch_ms": int(t["timestamp_msc"]),
            "timestamp_utc": t["timestamp_utc"],
            "bid": float(t["bid"]),
            "ask": float(t["ask"]),
        }
        ticks_by_bar.setdefault(bar_t, []).append(row)

    return {
        "day": day,
        "bars": bars,
        "ticks": ticks,
        "ticks_by_bar": ticks_by_bar,
        "m5_n": len(bars),
        "tick_n": len(ticks),
        "tick_window_start": tick_start,
        "tick_window_end": tick_end,
        "tick_window_declared": f"{TICK_WINDOW_START_HOUR:02d}:00–{TICK_WINDOW_END_HOUR:02d}:00 UTC",
        "missing_m5_unexpected_gaps": missing,
        "spread_median": _pct(spreads, 50),
        "spread_p95": _pct(spreads, 95),
        "spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
        "data_quality_status": quality,
        "candidate_eligibility_note": (
            "Tick-path trades eligible only if entry bar and all H12 holding bars have ticks "
            f"inside {TICK_WINDOW_START_HOUR:02d}:00–{TICK_WINDOW_END_HOUR:02d}:00 UTC"
        ),
    }


def build_eligibility_table(days: list[str] | None = None) -> dict[str, Any]:
    days = days or list_phase38_days()
    rows = []
    for day in days:
        d = load_day(day)
        rows.append(
            {
                "day": day,
                "available_m5_bars": d["m5_n"],
                "tick_window_start": d["tick_window_start"],
                "tick_window_end": d["tick_window_end"],
                "tick_count": d["tick_n"],
                "missing_intervals_unexpected": d["missing_m5_unexpected_gaps"],
                "spread_median": d["spread_median"],
                "spread_p95": d["spread_p95"],
                "data_quality_status": d["data_quality_status"],
                "candidate_eligibility": (
                    "PARTIAL_TICK_WINDOW_ONLY"
                    if d["m5_n"] > 0 and d["tick_n"] > 0
                    else "INELIGIBLE"
                ),
            }
        )
    return {
        "n_dates": len(rows),
        "rows": rows,
        "caveat": "Phase38 is NOT continuous coverage; ticks only 12:00–15:00 UTC per date.",
    }
