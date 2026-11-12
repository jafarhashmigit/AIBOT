"""Causal indicator helpers for Phase 30 (closed-bar only; no future bars)."""

from __future__ import annotations

import math
from typing import Any


def closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["close"]) for b in bars]


def highs(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["high"]) for b in bars]


def lows(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["low"]) for b in bars]


def opens(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["open"]) for b in bars]


def sma(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def ema_last(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    for x in vals[n:]:
        e = x * k + e * (1.0 - k)
    return e


def ema_series(vals: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1.0 - k)
        out[i] = e
    return out


def rolling_std(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    w = vals[-n:]
    mu = sum(w) / n
    var = sum((x - mu) ** 2 for x in w) / n
    return math.sqrt(var)


def median(vals: list[float]) -> float:
    xs = sorted(vals)
    m = len(xs)
    mid = m // 2
    if m % 2:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


def mad_zscore(vals: list[float], n: int) -> float | None:
    """Robust z = (x - median) / (1.4826 * MAD)."""
    if len(vals) < n:
        return None
    w = vals[-n:]
    med = median(w)
    abs_dev = [abs(x - med) for x in w]
    mad = median(abs_dev)
    scale = 1.4826 * mad
    if scale <= 1e-12:
        return 0.0
    return (vals[-1] - med) / scale


def ols_residual(vals: list[float], n: int) -> float | None:
    """Residual of last point vs OLS trend fit on last n points (inclusive)."""
    if len(vals) < n:
        return None
    y = vals[-n:]
    # x = 0..n-1
    sx = (n - 1) * n / 2.0
    sx2 = (n - 1) * n * (2 * n - 1) / 6.0
    sy = sum(y)
    sxy = sum(i * y[i] for i in range(n))
    den = n * sx2 - sx * sx
    if abs(den) <= 1e-12:
        return 0.0
    slope = (n * sxy - sx * sy) / den
    intercept = (sy - slope * sx) / n
    yhat = intercept + slope * (n - 1)
    return y[-1] - yhat


def residual_z(vals: list[float], trend_n: int, z_n: int) -> float | None:
    if len(vals) < max(trend_n, z_n) + 1:
        return None
    resids: list[float] = []
    for end in range(len(vals) - z_n + 1, len(vals) + 1):
        chunk = vals[:end]
        r = ols_residual(chunk, trend_n)
        if r is None:
            return None
        resids.append(r)
    return mad_zscore(resids, len(resids))


def atr_proxy(bars: list[dict[str, Any]], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(-n, 0):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        prev_c = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return sum(trs) / n


def range_mean(bars: list[dict[str, Any]], n: int) -> float | None:
    if len(bars) < n:
        return None
    return sum(float(b["high"]) - float(b["low"]) for b in bars[-n:]) / n


def directional_imbalance(bars: list[dict[str, Any]], n: int) -> float | None:
    """Fraction of bars with close > open over last n (0..1)."""
    if len(bars) < n:
        return None
    up = sum(1 for b in bars[-n:] if float(b["close"]) > float(b["open"]))
    return up / n


def body_range_ratio(bar: dict[str, Any]) -> float:
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    rng = h - l
    if rng <= 1e-12:
        return 0.0
    return abs(c - o) / rng


def upper_wick_ratio(bar: dict[str, Any]) -> float:
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    rng = h - l
    if rng <= 1e-12:
        return 0.0
    return (h - max(o, c)) / rng


def lower_wick_ratio(bar: dict[str, Any]) -> float:
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    rng = h - l
    if rng <= 1e-12:
        return 0.0
    return (min(o, c) - l) / rng


def m15_closes_from_m5(bars: list[dict[str, Any]]) -> list[float]:
    """Aggregate closed M5 triplets into M15 closes (no partial current M15)."""
    n = len(bars)
    start = n % 3
    out: list[float] = []
    i = start
    while i + 3 <= n:
        chunk = bars[i : i + 3]
        out.append(float(chunk[-1]["close"]))
        i += 3
    return out


def utc_hour(decision_time: str) -> int:
    return int(decision_time[11:13])


def percentile_rank(vals: list[float], x: float) -> float:
    if not vals:
        return float("nan")
    below = sum(1 for v in vals if v <= x)
    return below / len(vals)
