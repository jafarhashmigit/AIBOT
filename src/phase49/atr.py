"""ATR on completed bars only."""

from __future__ import annotations

from typing import Any


def atr_at(m5: list[dict[str, Any]], idx: int, period: int = 14) -> float | None:
    if idx + 1 < period or idx >= len(m5):
        return None
    trs = []
    for i in range(idx - period + 1, idx + 1):
        high = float(m5[i]["high"])
        low = float(m5[i]["low"])
        prev = float(m5[i - 1]["close"]) if i > 0 else None
        if prev is None:
            trs.append(high - low)
        else:
            trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    return sum(trs) / period
