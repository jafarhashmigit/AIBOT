"""Regime-based router: past-only regime labels + regime-specific rules."""

from __future__ import annotations

from typing import Any

from phase25.constants import STRATEGY_PARAMS
from phase25.indicators import closes, zscore
from phase25.strategies.mean_reversion import decide_mean_reversion

P = STRATEGY_PARAMS["regime_router"]


def classify_regime(feat: dict[str, Any]) -> str:
    spread = abs(float(feat["ema_9_20_spread"]))
    atr_pct = float(feat["atr_14_pct"])
    if atr_pct >= float(P["atr_pct_highvol"]):
        return "high_vol"
    if spread >= float(P["ema_spread_trend"]):
        return "trending"
    return "ranging"


def decide_regime_router(ctx: dict[str, Any]) -> tuple[str, str]:
    feat = ctx["feat"]
    h1 = ctx.get("h1_ctx") or {}
    regime = classify_regime(feat)
    c = closes(ctx["bars"])
    z = zscore(c, 40)
    if z is None:
        return "WAIT", "insufficient_history"

    if regime == "high_vol":
        return "WAIT", "high_vol_stand_aside"

    if regime == "trending":
        trend = h1.get("h1_trend")
        thr = float(P["trend_pullback_z"])
        if trend == "up" and z <= -thr and float(feat["ema_9_20_spread"]) > 0:
            return "BUY", "trend_pullback_buy"
        if trend == "down" and z >= thr and float(feat["ema_9_20_spread"]) < 0:
            return "SELL", "trend_pullback_sell"
        return "WAIT", "trend_no_pullback"

    action, reason = decide_mean_reversion(ctx)
    if action == "WAIT":
        return "WAIT", f"range_{reason}"
    return action, f"range_{reason}"
