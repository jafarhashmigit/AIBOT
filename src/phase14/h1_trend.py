"""Independent causal H1 EMA20 trend context.

Rewritten for Phase 14. Same economic definition as the Phase 13 plan:
SMA seed on the first 20 closed H1 bars, then EMA with alpha=2/21.
Only fully closed H1 bars (open_time + 1h <= decision_time) are visible.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def build_h1_series(h1_rows: list[dict]) -> list[dict]:
    series = []
    window: list[float] = []
    ema = None
    alpha = 2.0 / 21.0
    for row in h1_rows:
        close = float(row["close"])
        window.append(close)
        if len(window) < 20:
            ema = None
        elif len(window) == 20:
            ema = sum(window) / 20.0
        else:
            ema = alpha * close + (1.0 - alpha) * float(ema)
        series.append({
            "open_time": row["time"],
            "close_time": _fmt(_parse(row["time"]) + timedelta(hours=1)),
            "close": close,
            "ema20": ema,
        })
    return series


def h1_trend_at(series: list[dict], decision_time: str, *, strict_gt: bool = True) -> dict | None:
    """Binary-search the last closed H1 bar available at decision_time."""
    lo, hi = 0, len(series) - 1
    best = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if series[mid]["close_time"] <= decision_time:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    # Walk left to a bar with defined ema20 if needed
    while best >= 0 and series[best]["ema20"] is None:
        best -= 1
    if best < 0:
        return None
    bar = series[best]
    if strict_gt:
        up = bar["close"] > bar["ema20"]
    else:
        up = bar["close"] >= bar["ema20"]
    return {
        "h1_open_time": bar["open_time"],
        "h1_close": bar["close"],
        "h1_ema20": bar["ema20"],
        "h1_trend": "up" if up else "down",
        "strict_gt": strict_gt,
    }
