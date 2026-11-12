"""D: Rolling OLS residual-to-trend mean reversion."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import closes, residual_z

P = STRATEGY_PARAMS["regression_residual_mr"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    c = closes(ctx["bars"])
    z = residual_z(c, int(P["trend_n"]), int(P["resid_z_n"]))
    if z is None:
        return "WAIT", "insufficient_history", 0.0
    thr = float(P["entry_z"])
    strength = abs(z)
    if z <= -thr:
        return "BUY", "resid_oversold", strength
    if z >= thr:
        return "SELL", "resid_overbought", strength
    return "WAIT", "no_resid_signal", strength
