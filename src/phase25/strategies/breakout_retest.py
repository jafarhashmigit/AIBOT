"""Breakout + retest: Donchian channel break with false-break filter (independent)."""

from __future__ import annotations

from typing import Any

from phase25.constants import STRATEGY_PARAMS
from phase25.indicators import closes, donchian, highs, lows

P = STRATEGY_PARAMS["breakout_retest"]


def decide_breakout_retest(ctx: dict[str, Any]) -> tuple[str, str]:
    bars = ctx["bars"]
    feat = ctx["feat"]
    h = highs(bars)
    l = lows(bars)
    c = closes(bars)
    n = int(P["donchian_n"])
    upper, lower = donchian(h, l, n)
    if upper is None or lower is None:
        return "WAIT", "insufficient_donchian"
    atr_pct = float(feat["atr_14_pct"])
    price = float(feat["close"])
    look = int(P["false_break_lookback"])
    if len(c) > look + 1:
        if any(c[-1 - i] > upper for i in range(1, look + 1)) and c[-1] <= upper:
            return "WAIT", "false_break_long"
        if any(c[-1 - i] < lower for i in range(1, look + 1)) and c[-1] >= lower:
            return "WAIT", "false_break_short"
    min_break = float(P["min_break_atr_pct"]) * atr_pct * price
    tol = float(P["retest_tol_atr_pct"]) * atr_pct * price
    o = float(feat["open"])
    hi = float(feat["high"])
    lo = float(feat["low"])
    if c[-1] > upper + min_break and lo <= upper + tol and o <= upper + 2 * tol:
        return "BUY", "donchian_break_retest_long"
    if c[-1] < lower - min_break and hi >= lower - tol and o >= lower - 2 * tol:
        return "SELL", "donchian_break_retest_short"
    return "WAIT", "no_breakout_retest"
