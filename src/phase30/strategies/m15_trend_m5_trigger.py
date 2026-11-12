"""H: M15 trend from closed M5 aggregates + M5 pullback/confirm trigger."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import atr_proxy, closes, ema_last, m15_closes_from_m5

P = STRATEGY_PARAMS["m15_trend_m5_trigger"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    bars = ctx["bars"]
    m15 = m15_closes_from_m5(bars)
    n_ema = int(P["m15_ema"])
    if len(m15) < n_ema + 2:
        return "WAIT", "insufficient_m15", 0.0
    e = ema_last(m15, n_ema)
    e_prev = ema_last(m15[:-1], n_ema)
    if e is None or e_prev is None:
        return "WAIT", "m15_ema_unavailable", 0.0
    atr = atr_proxy(bars, 14)
    if atr is None or atr <= 1e-12:
        return "WAIT", "atr_unavailable", 0.0
    trend_up = e > e_prev
    trend_dn = e < e_prev
    c = closes(bars)
    conf = int(P["m5_confirm_bars"])
    if len(c) < conf + 2:
        return "WAIT", "insufficient_m5", 0.0
    pull = float(P["m5_pullback_atr"])
    # Pullback: recent dip against trend then confirm in trend direction
    move = (c[-1] - c[-1 - conf]) / atr
    strength = abs(move)
    if trend_up:
        # dipped within lookback then closed up
        dip = min(c[-conf - 1 :])
        if (c[-1] - dip) / atr >= pull and move > 0:
            return "BUY", "m15_up_m5_confirm", strength
    if trend_dn:
        rally = max(c[-conf - 1 :])
        if (rally - c[-1]) / atr >= pull and move < 0:
            return "SELL", "m15_dn_m5_confirm", strength
    return "WAIT", "no_mtf_trigger", strength
