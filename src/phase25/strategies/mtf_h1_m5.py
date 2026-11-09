"""Multi-timeframe H1 bias + M5 confirmation (EMA/RSI; not H13_C cuts)."""

from __future__ import annotations

from typing import Any

from phase25.constants import STRATEGY_PARAMS

P = STRATEGY_PARAMS["mtf_h1_m5"]


def decide_mtf_h1_m5(ctx: dict[str, Any]) -> tuple[str, str]:
    feat = ctx["feat"]
    h1 = ctx.get("h1_ctx")
    if not h1:
        return "WAIT", "missing_h1"
    trend = h1.get("h1_trend")
    rsi = float(feat.get("rsi_14") or 50)
    spread = float(feat["ema_9_20_spread"])
    if P["require_h1_align"] and trend not in {"up", "down"}:
        return "WAIT", "unknown_h1"
    if trend == "up":
        if rsi <= float(P["m5_rsi_buy_max"]) and spread > float(P["ema_spread_confirm"]):
            return "BUY", "h1_up_m5_rsi_ema"
        return "WAIT", "h1_up_no_m5_confirm"
    if trend == "down":
        if rsi >= float(P["m5_rsi_sell_min"]) and spread < -float(P["ema_spread_confirm"]):
            return "SELL", "h1_down_m5_rsi_ema"
        return "WAIT", "h1_down_no_m5_confirm"
    return "WAIT", "no_mtf"
