"""Causal indicator helpers for Phase 25 (closed-bar only)."""

from __future__ import annotations

import math
from typing import Any


def closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["close"]) for b in bars]


def highs(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["high"]) for b in bars]


def lows(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["low"]) for b in bars]


def sma(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def zscore(vals: list[float], n: int) -> float | None:
    if len(vals) < n:
        return None
    window = vals[-n:]
    mu = sum(window) / n
    var = sum((x - mu) ** 2 for x in window) / n
    sd = math.sqrt(var)
    if sd <= 1e-12:
        return 0.0
    return (vals[-1] - mu) / sd


def donchian(high_vals: list[float], low_vals: list[float], n: int) -> tuple[float | None, float | None]:
    if len(high_vals) < n + 1:
        return None, None
    prior_h = high_vals[-(n + 1) : -1]
    prior_l = low_vals[-(n + 1) : -1]
    return max(prior_h), min(prior_l)


def swing_points(
    high_vals: list[float], low_vals: list[float], lookback: int = 3
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    sh: list[tuple[int, float]] = []
    sl: list[tuple[int, float]] = []
    n = len(high_vals)
    for i in range(lookback, n - lookback):
        if all(
            high_vals[i] >= high_vals[i - j] and high_vals[i] >= high_vals[i + j]
            for j in range(1, lookback + 1)
        ):
            sh.append((i, high_vals[i]))
        if all(
            low_vals[i] <= low_vals[i - j] and low_vals[i] <= low_vals[i + j]
            for j in range(1, lookback + 1)
        ):
            sl.append((i, low_vals[i]))
    return sh, sl


def bullish_fvg(bars: list[dict[str, Any]], min_gap: float) -> bool:
    if len(bars) < 3:
        return False
    c0, c1, c2 = bars[-3], bars[-2], bars[-1]
    gap = float(c2["low"]) - float(c0["high"])
    return gap >= min_gap


def bearish_fvg(bars: list[dict[str, Any]], min_gap: float) -> bool:
    if len(bars) < 3:
        return False
    c0, c1, c2 = bars[-3], bars[-2], bars[-1]
    gap = float(c0["low"]) - float(c2["high"])
    return gap >= min_gap
