"""ATR on completed M5 bars only — no lookahead past decision bar."""

from __future__ import annotations

from typing import Any


def true_range(high: float, low: float, prev_close: float | None) -> float:
    if prev_close is None:
        return high - low
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr_at_bar(m5: list[dict[str, Any]], idx: int, period: int) -> float | None:
    """
    Wilder-style simple mean ATR using bars[0..idx] inclusive.
    Requires at least `period` completed bars ending at idx.
    """
    if idx < 0 or idx >= len(m5) or period <= 0:
        return None
    if idx + 1 < period:
        return None
    trs: list[float] = []
    for i in range(idx - period + 1, idx + 1):
        high = float(m5[i]["high"])
        low = float(m5[i]["low"])
        prev_close = float(m5[i - 1]["close"]) if i > 0 else None
        trs.append(true_range(high, low, prev_close))
    if len(trs) < period:
        return None
    return sum(trs) / period
