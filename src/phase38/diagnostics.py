"""Spread and session diagnostics (MetaQuotes-Demo descriptive only)."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def spread_diagnostics(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    spreads = []
    by_hour: dict[int, list[float]] = defaultdict(list)
    by_weekday: dict[str, list[float]] = defaultdict(list)
    by_date: dict[str, list[float]] = defaultdict(list)
    ticks_by_hour: dict[int, int] = defaultdict(int)

    for t in ticks:
        bid, ask = t.get("bid"), t.get("ask")
        if bid is None or ask is None:
            continue
        sp = float(ask) - float(bid)
        spreads.append(sp)
        ts = t.get("timestamp_utc") or ""
        try:
            # support with/without millis
            base = ts.split(".")[0]
            dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
            by_hour[dt.hour].append(sp)
            by_weekday[dt.strftime("%A")].append(sp)
            by_date[dt.strftime("%Y-%m-%d")].append(sp)
            ticks_by_hour[dt.hour] += 1
        except ValueError:
            continue

    def summarize(vals: list[float]) -> dict[str, Any]:
        return {
            "n": len(vals),
            "median": _pct(vals, 50),
            "mean": (sum(vals) / len(vals)) if vals else None,
            "p75": _pct(vals, 75),
            "p90": _pct(vals, 90),
            "p95": _pct(vals, 95),
            "p99": _pct(vals, 99),
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
        }

    return {
        "units": "price units (XAUUSD quote); NOT assumed USD per side; NOT points unless divided by point=0.01",
        "point_size": 0.01,
        "overall": summarize(spreads),
        "by_utc_hour_median": {str(h): _pct(v, 50) for h, v in sorted(by_hour.items())},
        "by_weekday_median": {k: _pct(v, 50) for k, v in sorted(by_weekday.items())},
        "by_date_median": {k: _pct(v, 50) for k, v in sorted(by_date.items())},
        "tick_count_by_utc_hour": {str(h): n for h, n in sorted(ticks_by_hour.items())},
        "source_caveat": "MetaQuotes-Demo descriptive only; not live broker execution truth",
    }
