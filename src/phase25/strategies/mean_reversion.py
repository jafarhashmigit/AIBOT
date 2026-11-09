"""Mean-reversion hypothesis: Z-score + RSI + volatility filters (independent)."""

from __future__ import annotations

from typing import Any

from phase25.constants import STRATEGY_PARAMS
from phase25.indicators import closes, zscore

P = STRATEGY_PARAMS["mean_reversion"]


def decide_mean_reversion(ctx: dict[str, Any]) -> tuple[str, str]:
    feat = ctx["feat"]
    bars = ctx["bars"]
    c = closes(bars)
    z = zscore(c, int(P["z_window"]))
    if z is None:
        return "WAIT", "insufficient_history"
    atr_pct = float(feat["atr_14_pct"])
    if atr_pct < float(P["atr_pct_min"]) or atr_pct > float(P["atr_pct_max"]):
        return "WAIT", "atr_filter"
    vol_ratio = float(feat.get("volatility_ratio_12_48") or 0)
    if vol_ratio > float(P["vol_ratio_max"]):
        return "WAIT", "vol_ratio_trendish"
    rsi = float(feat.get("rsi_14") or 50)
    if z <= -float(P["z_entry"]) and rsi <= float(P["rsi_buy_max"]):
        return "BUY", "z_rsi_buy"
    if z >= float(P["z_entry"]) and rsi >= float(P["rsi_sell_min"]):
        return "SELL", "z_rsi_sell"
    return "WAIT", "no_mean_reversion"
