"""Non-overlapping H12 bid/ask outcomes (Phase46 conventions)."""

from __future__ import annotations

from typing import Any

from phase46.cost_scenarios import COST_SCENARIO_REGISTRY, apply_scenario_costs
from phase49.atr import atr_at
from phase49.constants import ATR_PERIOD, HORIZON_BARS, MIN_ATR


def build_outcome(
    *,
    action: str,
    day: str,
    decision_idx: int,
    m5: list[dict[str, Any]],
    ticks_by_bar: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    assert action in ("BUY", "SELL")
    entry_idx = decision_idx + 1
    exit_idx = entry_idx + HORIZON_BARS - 1
    atr = atr_at(m5, decision_idx, ATR_PERIOD)
    base = {
        "day": day,
        "decision_bar": str(m5[decision_idx]["timestamp_utc"]),
        "decision_idx": decision_idx,
        "action": action,
        "horizon_bars": HORIZON_BARS,
    }
    if atr is None or atr <= MIN_ATR or entry_idx >= len(m5) or exit_idx >= len(m5):
        return {**base, "data_quality_status": "INCOMPLETE_OR_INVALID_RISK", "net_r": None}

    entry_bar = str(m5[entry_idx]["timestamp_utc"])
    exit_bar = str(m5[exit_idx]["timestamp_utc"])
    for j in range(entry_idx, exit_idx + 1):
        if not ticks_by_bar.get(str(m5[j]["timestamp_utc"])):
            return {**base, "data_quality_status": "MISSING_PATH_TICKS", "net_r": None, "entry_bar": entry_bar}

    e0 = ticks_by_bar[entry_bar][0]
    x0 = ticks_by_bar[exit_bar][-1]
    entry_bid, entry_ask = float(e0["bid"]), float(e0["ask"])
    exit_bid, exit_ask = float(x0["bid"]), float(x0["ask"])
    if action == "BUY":
        entry_fill, exit_fill = entry_ask, exit_bid
        gross_pnl = exit_fill - entry_fill
    else:
        entry_fill, exit_fill = entry_bid, exit_ask
        gross_pnl = entry_fill - exit_fill

    risk = float(atr)
    entry_spread = entry_ask - entry_bid
    exit_spread = exit_ask - exit_bid
    scenarios = {
        sid: apply_scenario_costs(
            gross_pnl=gross_pnl,
            risk_amount=risk,
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            scenario=sc,
        )
        for sid, sc in COST_SCENARIO_REGISTRY.items()
    }
    observed = scenarios["OBSERVED_BIDASK_ONLY"]
    return {
        **base,
        "entry_bar": entry_bar,
        "exit_bar": exit_bar,
        "entry_timestamp": e0["timestamp_utc"],
        "exit_timestamp": x0["timestamp_utc"],
        "entry_bid": entry_bid,
        "entry_ask": entry_ask,
        "exit_bid": exit_bid,
        "exit_ask": exit_ask,
        "entry_fill": entry_fill,
        "exit_fill": exit_fill,
        "gross_pnl": gross_pnl,
        "risk_amount": risk,
        "gross_r": gross_pnl / risk,
        "commission": None,
        "slippage": None,
        "net_pnl": observed["net_pnl"],
        "net_r": observed["net_r"],
        "scenario_nets": scenarios,
        "mid_price_used": False,
        "data_quality_status": "OK",
        "exit_reason": "HORIZON_EXIT",
    }
