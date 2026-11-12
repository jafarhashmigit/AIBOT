"""J: Simple agreement ensemble — vol-norm momentum + wick structure."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.strategies import vol_norm_momentum, wick_exhaustion

P = STRATEGY_PARAMS["momentum_structure_ensemble"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    # Temporarily override entry thresholds via shallow param shadowing is not allowed;
    # call base decides and require agreement; apply ensemble-specific strength gates.
    a1, r1, s1 = vol_norm_momentum.decide(ctx)
    a2, r2, s2 = wick_exhaustion.decide(ctx)
    strength = 0.5 * (abs(s1) + abs(s2))
    if a1 in {"BUY", "SELL"} and a1 == a2:
        # Ensemble-specific soft thresholds on component strengths
        if a1 == "BUY" and s1 >= float(P["mom_entry_z"]) * 0.5 and s2 >= 0.0:
            return "BUY", "ensemble_agree_buy", strength
        if a1 == "SELL" and s1 >= float(P["mom_entry_z"]) * 0.5 and s2 >= 0.0:
            return "SELL", "ensemble_agree_sell", strength
        if a1 == a2:
            return a1, "ensemble_agree", strength
    if a1 in {"BUY", "SELL"} and a2 == "WAIT":
        return "WAIT", f"ensemble_mom_only:{r1}", strength
    if a2 in {"BUY", "SELL"} and a1 == "WAIT":
        return "WAIT", f"ensemble_wick_only:{r2}", strength
    return "WAIT", "ensemble_no_agree", strength
