"""Reusable cost-sensitivity evaluator for future candidates — no H70/C07_A screening."""

from __future__ import annotations

from typing import Any

from signal_bot.execution_economics.constants import (
    SENSITIVITY_VERSION,
    UNKNOWN,
    VERIFIED_TICK_VALUE,
    canonical_json_sha256,
)
from signal_bot.execution_economics.cost_model import apply_costs_to_trade_r


def evaluate_trade_cost_sensitivity(
    *,
    entry: float,
    stop_loss: float,
    take_profit: float,
    holding_bars: int,
    direction: str,
    observed_spread_price: float | None,
    commission_r: float | None = None,
    swap_r_per_night: float | None = None,
    nights: int = 0,
    slippage_r: float | None = None,
    cost_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Given proposed entry/SL/TP/hold, compute gross R metrics and cost sensitivity.

    commission_r / swap_r / slippage_r must be None when unverified — never default to 0.
    """
    d = direction.upper()
    if d not in ("BUY", "SELL"):
        raise ValueError("direction must be BUY or SELL")
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    if risk <= 0:
        raise ValueError("stop distance must be > 0")

    reward_risk = reward / risk
    # Gross R if TP or SL hit (binary outcomes)
    gross_win_r = reward_risk
    gross_loss_r = -1.0

    spread_impact_r = (observed_spread_price / risk) if observed_spread_price is not None else None
    commission_impact = commission_r  # already in R or None
    swap_impact = None
    if nights <= 0:
        # Intraday: overnight swap not applicable (distinct from UNKNOWN commission)
        swap_impact = None
        swap_applicable = False
    elif swap_r_per_night is not None:
        swap_impact = float(swap_r_per_night) * nights
        swap_applicable = True
    else:
        swap_applicable = True  # applicable but unverified

    cm = cost_model or {
        "known_cost_adjusted_r_supported": observed_spread_price is not None,
        "NET_PROFITABILITY": "NOT_ESTABLISHED",
    }

    win_adj = apply_costs_to_trade_r(
        gross_r=gross_win_r,
        risk_price=risk,
        spread_price=observed_spread_price,
        commission_r=commission_impact,
        swap_r=swap_impact,
        slippage_r=slippage_r,
        cost_model=cm,
    )
    loss_adj = apply_costs_to_trade_r(
        gross_r=gross_loss_r,
        risk_price=risk,
        spread_price=observed_spread_price,
        commission_r=commission_impact,
        swap_r=swap_impact,
        slippage_r=slippage_r,
        cost_model=cm,
    )

    # Break-even win rate for binary TP/SL: wr*W + (1-wr)*L = 0 => wr = -L/(W-L)
    def _be(win_r: float, loss_r: float) -> float | None:
        denom = win_r - loss_r
        if denom == 0:
            return None
        return (-loss_r) / denom

    be_gross = _be(gross_win_r, gross_loss_r)
    be_known = None
    if win_adj["known_cost_adjusted_r"] is not None and loss_adj["known_cost_adjusted_r"] is not None:
        be_known = _be(win_adj["known_cost_adjusted_r"], loss_adj["known_cost_adjusted_r"])

    # Max tolerable total execution cost in R such that expectancy at 50% WR is zero:
    # 0.5*(W-c) + 0.5*(-1-c) = 0 => c = (W-1)/2
    max_tol_cost_r_at_50 = (gross_win_r - 1.0) / 2.0

    # Break-even average R:R for fixed 50% WR with cost c: need W such that 0.5W - 0.5 = c => W = 1+2c
    spread_c = spread_impact_r or 0.0
    # Only for hypothetical illustration when spread known; label clearly
    be_rr_at_50_with_spread = (1.0 + 2.0 * spread_c) if observed_spread_price is not None else UNKNOWN

    out = {
        "sensitivity_version": SENSITIVITY_VERSION,
        "inputs": {
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "holding_bars": holding_bars,
            "direction": d,
            "nights": nights,
            "observed_spread_price": observed_spread_price,
            "commission_r": commission_impact if commission_impact is not None else UNKNOWN,
            "swap_r": swap_impact if swap_impact is not None else ("NOT_APPLICABLE" if not swap_applicable else UNKNOWN),
            "swap_applicable": swap_applicable,
            "slippage_r": slippage_r if slippage_r is not None else UNKNOWN,
        },
        "gross_reward": reward,
        "gross_risk": risk,
        "gross_reward_risk": reward_risk,
        "gross_win_r": gross_win_r,
        "gross_loss_r": gross_loss_r,
        "spread_impact_r": spread_impact_r if spread_impact_r is not None else UNKNOWN,
        "commission_impact_r": commission_impact if commission_impact is not None else UNKNOWN,
        "swap_impact_r": swap_impact if swap_impact is not None else UNKNOWN,
        "win_path": win_adj,
        "loss_path": loss_adj,
        "break_even_win_rate_gross": be_gross,
        "break_even_win_rate_known_cost_adjusted": be_known,
        "break_even_avg_reward_risk_at_50pct_with_observed_spread_only": be_rr_at_50_with_spread,
        "max_tolerable_total_execution_cost_r_at_50pct_wr": max_tol_cost_r_at_50,
        "observed_vs_scenario": {
            "observed_spread_used": observed_spread_price is not None,
            "commission_is_scenario": commission_impact is not None and cm.get("NET_PROFITABILITY") != "ESTABLISHED",
            "slippage_is_scenario": slippage_r is not None,
            "note": "Scenario assumptions never labeled as actual broker costs",
        },
        "tick_value_reference": VERIFIED_TICK_VALUE,
        "forbids": ["retune_H70", "screen_C07_A_on_consumed_archives"],
        "sha256": None,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
