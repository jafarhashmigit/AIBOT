"""C: Robust median/MAD mean reversion (not Phase25 mean/std z+RSI)."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import closes, mad_zscore

P = STRATEGY_PARAMS["robust_mad_reversion"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    feat = ctx["feat"]
    c = closes(ctx["bars"])
    z = mad_zscore(c, int(P["window"]))
    if z is None:
        return "WAIT", "insufficient_history", 0.0
    atr_pct = float(feat["atr_14_pct"])
    if atr_pct < float(P["atr_pct_min"]) or atr_pct > float(P["atr_pct_max"]):
        return "WAIT", "atr_filter", abs(z)
    thr = float(P["mad_entry"])
    strength = abs(z)
    if z <= -thr:
        return "BUY", "mad_oversold", strength
    if z >= thr:
        return "SELL", "mad_overbought", strength
    return "WAIT", "no_mad_reversion", strength
