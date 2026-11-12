"""F: Past ATR-percentile high-vol regime + short momentum trigger."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import atr_proxy, closes, percentile_rank

P = STRATEGY_PARAMS["regime_cond_momentum"]


def _rolling_atr_series(bars: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    """Single-pass Wilder-like mean TR series (causal)."""
    n = len(bars)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    trs: list[float] = []
    for i in range(1, n):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        prev_c = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        if len(trs) >= period:
            out[i] = sum(trs[-period:]) / period
    return out


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    bars = ctx["bars"]
    lb = int(P["atr_pct_lookback"])
    mom_n = int(P["mom_bars"])
    if len(bars) < lb + mom_n + 2:
        return "WAIT", "insufficient_history", 0.0
    atr_series = _rolling_atr_series(bars, 14)
    atr_now = atr_series[-1]
    if atr_now is None or atr_now <= 1e-12:
        atr_now = atr_proxy(bars, 14)
    if atr_now is None or atr_now <= 1e-12:
        return "WAIT", "atr_unavailable", 0.0
    # Past ATR distribution excluding current bar
    hist = [a for a in atr_series[-(lb + 1) : -1] if a is not None]
    if len(hist) < 20:
        return "WAIT", "atr_history_short", 0.0
    pct = percentile_rank(hist, float(atr_now))
    if pct < float(P["high_pctile"]):
        return "WAIT", "not_high_vol_regime", pct
    c = closes(bars)
    move = (c[-1] - c[-1 - mom_n]) / float(atr_now)
    thr = float(P["mom_atr_min"])
    strength = abs(move)
    if move >= thr:
        return "BUY", "highvol_mom_up", strength
    if move <= -thr:
        return "SELL", "highvol_mom_down", strength
    return "WAIT", "highvol_no_mom", strength
