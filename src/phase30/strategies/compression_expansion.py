"""B: Compression → expansion breakout (not Donchian retest)."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import atr_proxy, highs, lows, range_mean

P = STRATEGY_PARAMS["compression_expansion"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    bars = ctx["bars"]
    n = int(P["range_n"])
    if len(bars) < n + 6:
        return "WAIT", "insufficient_history", 0.0
    atr = atr_proxy(bars, 14)
    if atr is None or atr <= 1e-12:
        return "WAIT", "atr_unavailable", 0.0
    recent = range_mean(bars, n)
    prior = range_mean(bars[: -n], n)
    if recent is None or prior is None or prior <= 1e-12:
        return "WAIT", "range_unavailable", 0.0
    compress = recent / prior
    # Expansion: last bar range vs recent mean
    last_rng = float(bars[-1]["high"]) - float(bars[-1]["low"])
    expand = last_rng / max(recent, 1e-12)
    if compress > float(P["compress_ratio"]) or expand < float(P["expand_ratio"]):
        return "WAIT", "no_compress_expand", abs(1.0 - compress)
    # Prior range high/low excluding last bar
    h = highs(bars[-(n + 1) : -1])
    l = lows(bars[-(n + 1) : -1])
    if not h or not l:
        return "WAIT", "prior_range_missing", 0.0
    ph, pl = max(h), min(l)
    close = float(bars[-1]["close"])
    thr = float(P["break_atr_frac"]) * atr
    strength = expand
    if close > ph + thr:
        return "BUY", "expand_break_up", strength
    if close < pl - thr:
        return "SELL", "expand_break_down", strength
    return "WAIT", "expand_no_break", strength
