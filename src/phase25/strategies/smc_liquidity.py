"""SMC / liquidity-sweep hypothesis — independent non-repainting closed-bar rules."""

from __future__ import annotations

from typing import Any

from phase25.constants import STRATEGY_PARAMS
from phase25.indicators import bearish_fvg, bullish_fvg, highs, lows, swing_points

P = STRATEGY_PARAMS["smc_liquidity"]


def decide_smc_liquidity(ctx: dict[str, Any]) -> tuple[str, str]:
    bars = ctx["bars"]
    feat = ctx["feat"]
    lb = int(P["swing_lookback"])
    h = highs(bars)
    l = lows(bars)
    sh, sl = swing_points(h, l, lookback=lb)
    if len(sh) < 2 or len(sl) < 2:
        return "WAIT", "insufficient_swings"
    last_sh = sh[-1][1]
    last_sl = sl[-1][1]
    prev_sh = sh[-2][1]
    prev_sl = sl[-2][1]
    close = float(feat["close"])
    atr_pct = float(feat["atr_14_pct"])
    min_gap = float(P["fvg_min_atr_frac"]) * atr_pct * close

    swept_low = float(feat["low"]) < last_sl and close > last_sl
    swept_high = float(feat["high"]) > last_sh and close < last_sh

    bullish_bos = close > last_sh and last_sh > prev_sh
    bearish_bos = close < last_sl and last_sl < prev_sl
    was_bearish = last_sh < prev_sh and last_sl < prev_sl
    was_bullish = last_sh > prev_sh and last_sl > prev_sl
    bullish_choch = was_bearish and close > last_sh
    bearish_choch = was_bullish and close < last_sl

    bos_ok_long = (bullish_bos or bullish_choch) if P["require_bos"] else True
    bos_ok_short = (bearish_bos or bearish_choch) if P["require_bos"] else True

    if swept_low and bos_ok_long and bullish_fvg(bars, min_gap):
        return "BUY", "sweep_low_bos_fvg"
    if swept_high and bos_ok_short and bearish_fvg(bars, min_gap):
        return "SELL", "sweep_high_bos_fvg"
    return "WAIT", "no_smc_setup"
