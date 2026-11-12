"""E: Wick rejection sequences + body/range structure."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import atr_proxy, body_range_ratio, lower_wick_ratio, upper_wick_ratio

P = STRATEGY_PARAMS["wick_exhaustion"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    bars = ctx["bars"]
    n = int(P["seq_n"])
    if len(bars) < n + 2:
        return "WAIT", "insufficient_history", 0.0
    atr = atr_proxy(bars, 14)
    if atr is None or atr <= 1e-12:
        return "WAIT", "atr_unavailable", 0.0
    seq = bars[-n:]
    # Bullish exhaustion: long lower wicks, closing up
    lower = [lower_wick_ratio(b) for b in seq]
    upper = [upper_wick_ratio(b) for b in seq]
    bodies = [body_range_ratio(b) for b in seq]
    rng = float(bars[-1]["high"]) - float(bars[-1]["low"])
    if rng / atr < float(P["range_atr_min"]):
        return "WAIT", "range_too_small", 0.0
    thr = float(P["wick_body_min"])
    strength = max(sum(lower) / n, sum(upper) / n)
    bullish = all(lw >= thr * max(br, 0.05) for lw, br in zip(lower, bodies)) and float(
        bars[-1]["close"]
    ) > float(bars[-1]["open"])
    bearish = all(uw >= thr * max(br, 0.05) for uw, br in zip(upper, bodies)) and float(
        bars[-1]["close"]
    ) < float(bars[-1]["open"])
    if bullish and not bearish:
        return "BUY", "lower_wick_exhaustion", strength
    if bearish and not bullish:
        return "SELL", "upper_wick_exhaustion", strength
    return "WAIT", "no_wick_exhaustion", strength
