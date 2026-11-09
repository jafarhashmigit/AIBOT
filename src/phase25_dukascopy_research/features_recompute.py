"""Recompute OHLC-derived features for parity (does not modify Phase 14/16A)."""

from __future__ import annotations

import math
from typing import Any


def _ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    trs: list[float] = [0.0]
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    # Wilder
    atr = sum(trs[1 : period + 1]) / period
    out[period] = atr
    for i in range(period + 1, len(closes)):
        atr = (atr * (period - 1) + trs[i]) / period
        out[i] = atr
    return out


def recompute_row_features(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """bars require open,high,low,close and timestamp_utc or time."""
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    opens = [float(b["open"]) for b in bars]
    ema9 = _ema(closes, 9)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    atr = _atr(highs, lows, closes, 14)
    rows: list[dict[str, Any]] = []
    for i, b in enumerate(bars):
        c = closes[i]
        o = opens[i]
        h = highs[i]
        l = lows[i]
        body = c - o
        rng = h - l
        feat: dict[str, Any] = {
            "time": b.get("timestamp_utc") or b.get("time"),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "ema_9": ema9[i],
            "ema_20": ema20[i],
            "ema_50": ema50[i],
            "close_to_ema_9": None if ema9[i] is None else (c - ema9[i]) / ema9[i],
            "close_to_ema_20": None if ema20[i] is None else (c - ema20[i]) / ema20[i],
            "close_to_ema_50": None if ema50[i] is None else (c - ema50[i]) / ema50[i],
            "ema_9_20_spread": None
            if ema9[i] is None or ema20[i] is None
            else (ema9[i] - ema20[i]) / ema20[i],
            "ema_20_50_spread": None
            if ema20[i] is None or ema50[i] is None
            else (ema20[i] - ema50[i]) / ema50[i],
            "atr_14": atr[i],
            "atr_14_pct": None if atr[i] is None or c == 0 else atr[i] / c,
            "candle_body": body,
            "candle_body_abs": abs(body),
            "upper_wick": h - max(o, c),
            "lower_wick": min(o, c) - l,
            "candle_range": rng,
            "log_return_1": None if i == 0 or closes[i - 1] <= 0 else math.log(c / closes[i - 1]),
            "return_1": None if i == 0 else (c / closes[i - 1]) - 1.0,
            "return_3": None if i < 3 else (c / closes[i - 3]) - 1.0,
            "return_6": None if i < 6 else (c / closes[i - 6]) - 1.0,
            "return_12": None if i < 12 else (c / closes[i - 12]) - 1.0,
            "momentum_10": None if i < 10 else c - closes[i - 10],
            "roc_10": None if i < 10 or closes[i - 10] == 0 else (c / closes[i - 10]) - 1.0,
            "momentum_20": None if i < 20 else c - closes[i - 20],
            "roc_20": None if i < 20 or closes[i - 20] == 0 else (c / closes[i - 20]) - 1.0,
        }
        rows.append(feat)
    return rows
