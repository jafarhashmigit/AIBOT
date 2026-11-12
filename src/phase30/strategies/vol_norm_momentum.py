"""A: Volatility-normalized momentum + EMA slope acceleration."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import atr_proxy, closes, ema_last

P = STRATEGY_PARAMS["vol_norm_momentum"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    bars = ctx["bars"]
    c = closes(bars)
    n_ret = int(P["ret_bars"])
    n_vol = int(P["vol_bars"])
    if len(c) < max(n_ret, n_vol, int(P["ema_slow"])) + int(P["accel_lookback"]):
        return "WAIT", "insufficient_history", 0.0
    atr = atr_proxy(bars, 14)
    if atr is None or atr <= 1e-12:
        return "WAIT", "atr_unavailable", 0.0
    ret = (c[-1] - c[-1 - n_ret]) / atr
    vol = atr_proxy(bars, n_vol) or atr
    mom_z = ret / max(vol / atr, 1e-6)
    e_fast = ema_last(c, int(P["ema_fast"]))
    e_slow = ema_last(c, int(P["ema_slow"]))
    e_fast_prev = ema_last(c[: -int(P["accel_lookback"])], int(P["ema_fast"]))
    e_slow_prev = ema_last(c[: -int(P["accel_lookback"])], int(P["ema_slow"]))
    if None in (e_fast, e_slow, e_fast_prev, e_slow_prev):
        return "WAIT", "ema_unavailable", 0.0
    slope = (e_fast - e_slow) / atr
    slope_prev = (e_fast_prev - e_slow_prev) / atr
    accel = slope - slope_prev
    thr = float(P["entry_z"])
    strength = abs(mom_z)
    if mom_z >= thr and accel > 0 and slope > 0:
        return "BUY", "vol_norm_mom_up", strength
    if mom_z <= -thr and accel < 0 and slope < 0:
        return "SELL", "vol_norm_mom_down", strength
    return "WAIT", "no_momentum", strength
