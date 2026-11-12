"""Action-conditioned BUY/SELL/WAIT outcomes with bid/ask fills (primary)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from phase46.atr import atr_at_bar
from phase46.constants import ATR_PERIOD, HORIZON_BARS, MIN_ATR, RECIPE_ID, SYMBOL
from phase46.cost_scenarios import COST_SCENARIO_REGISTRY, apply_scenario_costs


OUTCOME_FIELDS = (
    "entry_timestamp",
    "exit_timestamp",
    "action",
    "entry_bid",
    "entry_ask",
    "exit_bid",
    "exit_ask",
    "gross_pnl",
    "risk_amount",
    "gross_r",
    "spread_cost_embedded",
    "commission",
    "slippage",
    "net_pnl",
    "net_r",
    "mfe",
    "mae",
    "exit_reason",
    "data_quality_status",
)


def _row_hash(row: dict[str, Any]) -> str:
    payload = {k: row.get(k) for k in OUTCOME_FIELDS}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _wait_outcome(
    *,
    day: str,
    decision_bar: str,
    entry_bar: str,
    exit_bar: str | None,
    risk_amount: float | None,
    dq: str,
) -> dict[str, Any]:
    row = {
        "recipe_id": RECIPE_ID,
        "symbol": SYMBOL,
        "day": day,
        "decision_bar": decision_bar,
        "entry_bar": entry_bar,
        "exit_bar": exit_bar,
        "entry_timestamp": None,
        "exit_timestamp": None,
        "action": "WAIT",
        "entry_bid": None,
        "entry_ask": None,
        "exit_bid": None,
        "exit_ask": None,
        "entry_fill": None,
        "exit_fill": None,
        "gross_pnl": 0.0,
        "risk_amount": risk_amount,
        "gross_r": 0.0 if risk_amount and risk_amount > 0 else None,
        "spread_cost_embedded": 0.0,
        "entry_spread": 0.0,
        "exit_spread": 0.0,
        "commission": 0.0,
        "slippage": 0.0,
        "net_pnl": 0.0,
        "net_r": 0.0 if risk_amount and risk_amount > 0 else None,
        "mfe": 0.0,
        "mae": 0.0,
        "exit_reason": "NO_POSITION",
        "data_quality_status": dq,
        "scenario_nets": {},
    }
    for sid, sc in COST_SCENARIO_REGISTRY.items():
        row["scenario_nets"][sid] = {
            "scenario_id": sid,
            "net_pnl": 0.0,
            "net_r": 0.0 if risk_amount and risk_amount > 0 else None,
            "total_modeled_extra_cost": 0.0,
            "unknown_cost_components": [],
            "note": "WAIT incurs no transaction cost in Phase46",
        }
    row["outcome_sha256"] = _row_hash(row)
    return row


def build_directional_outcome(
    *,
    action: str,
    day: str,
    decision_idx: int,
    m5: list[dict[str, Any]],
    ticks_by_bar: dict[str, list[dict[str, Any]]],
    horizon_bars: int = HORIZON_BARS,
    atr_period: int = ATR_PERIOD,
) -> dict[str, Any]:
    """BUY/SELL fixed-horizon bid/ask path. No mid fills. No lookahead ATR."""
    assert action in ("BUY", "SELL")
    decision_bar = str(m5[decision_idx]["timestamp_utc"])
    entry_idx = decision_idx + 1
    exit_idx = entry_idx + horizon_bars - 1

    atr = atr_at_bar(m5, decision_idx, atr_period)
    if atr is None or atr <= MIN_ATR:
        return {
            "recipe_id": RECIPE_ID,
            "symbol": SYMBOL,
            "day": day,
            "decision_bar": decision_bar,
            "entry_bar": str(m5[entry_idx]["timestamp_utc"]) if entry_idx < len(m5) else None,
            "exit_bar": str(m5[exit_idx]["timestamp_utc"]) if exit_idx < len(m5) else None,
            "action": action,
            "entry_timestamp": None,
            "exit_timestamp": None,
            "entry_bid": None,
            "entry_ask": None,
            "exit_bid": None,
            "exit_ask": None,
            "entry_fill": None,
            "exit_fill": None,
            "gross_pnl": None,
            "risk_amount": atr,
            "gross_r": None,
            "spread_cost_embedded": None,
            "entry_spread": None,
            "exit_spread": None,
            "commission": None,
            "slippage": None,
            "net_pnl": None,
            "net_r": None,
            "mfe": None,
            "mae": None,
            "exit_reason": "INVALID_RISK",
            "data_quality_status": "INVALID_RISK",
            "scenario_nets": {},
            "outcome_sha256": None,
        }

    if entry_idx >= len(m5) or exit_idx >= len(m5):
        return {
            "recipe_id": RECIPE_ID,
            "day": day,
            "decision_bar": decision_bar,
            "action": action,
            "exit_reason": "INCOMPLETE_HORIZON",
            "data_quality_status": "INCOMPLETE_HORIZON",
            "gross_pnl": None,
            "net_pnl": None,
            "net_r": None,
            "gross_r": None,
            "risk_amount": atr,
            "scenario_nets": {},
            "outcome_sha256": None,
            "entry_timestamp": None,
            "exit_timestamp": None,
            "entry_bid": None,
            "entry_ask": None,
            "exit_bid": None,
            "exit_ask": None,
            "mfe": None,
            "mae": None,
            "commission": None,
            "slippage": None,
            "spread_cost_embedded": None,
        }

    entry_bar = str(m5[entry_idx]["timestamp_utc"])
    exit_bar = str(m5[exit_idx]["timestamp_utc"])
    entry_ticks = ticks_by_bar.get(entry_bar) or []
    exit_ticks = ticks_by_bar.get(exit_bar) or []
    if not entry_ticks:
        row = {
            "recipe_id": RECIPE_ID,
            "day": day,
            "decision_bar": decision_bar,
            "entry_bar": entry_bar,
            "exit_bar": exit_bar,
            "action": action,
            "exit_reason": "MISSING_ENTRY_TICKS",
            "data_quality_status": "MISSING_ENTRY_TICKS",
            "gross_pnl": None,
            "net_r": None,
            "risk_amount": atr,
            "scenario_nets": {},
            "outcome_sha256": None,
            "entry_timestamp": None,
            "exit_timestamp": None,
            "entry_bid": None,
            "entry_ask": None,
            "exit_bid": None,
            "exit_ask": None,
            "gross_r": None,
            "net_pnl": None,
            "mfe": None,
            "mae": None,
            "commission": None,
            "slippage": None,
            "spread_cost_embedded": None,
        }
        return row
    if not exit_ticks:
        return {
            "recipe_id": RECIPE_ID,
            "day": day,
            "decision_bar": decision_bar,
            "entry_bar": entry_bar,
            "exit_bar": exit_bar,
            "action": action,
            "exit_reason": "MISSING_EXIT_TICKS",
            "data_quality_status": "MISSING_EXIT_TICKS",
            "gross_pnl": None,
            "net_r": None,
            "risk_amount": atr,
            "scenario_nets": {},
            "outcome_sha256": None,
            "entry_timestamp": None,
            "exit_timestamp": None,
            "entry_bid": None,
            "entry_ask": None,
            "exit_bid": None,
            "exit_ask": None,
            "gross_r": None,
            "net_pnl": None,
            "mfe": None,
            "mae": None,
            "commission": None,
            "slippage": None,
            "spread_cost_embedded": None,
        }

    # Ensure all intermediate bars have ticks (integrity; no fabricate)
    missing_bars = []
    path: list[dict[str, Any]] = []
    for j in range(entry_idx, exit_idx + 1):
        bt = str(m5[j]["timestamp_utc"])
        bticks = ticks_by_bar.get(bt) or []
        if not bticks:
            missing_bars.append(bt)
        else:
            path.extend(bticks)
    if missing_bars:
        return {
            "recipe_id": RECIPE_ID,
            "day": day,
            "decision_bar": decision_bar,
            "entry_bar": entry_bar,
            "exit_bar": exit_bar,
            "action": action,
            "exit_reason": "MISSING_PATH_TICKS",
            "data_quality_status": "MISSING_PATH_TICKS",
            "missing_bars": missing_bars[:24],
            "n_missing_bars": len(missing_bars),
            "gross_pnl": None,
            "net_r": None,
            "risk_amount": atr,
            "scenario_nets": {},
            "outcome_sha256": None,
            "entry_timestamp": None,
            "exit_timestamp": None,
            "entry_bid": None,
            "entry_ask": None,
            "exit_bid": None,
            "exit_ask": None,
            "gross_r": None,
            "net_pnl": None,
            "mfe": None,
            "mae": None,
            "commission": None,
            "slippage": None,
            "spread_cost_embedded": None,
        }

    e0 = entry_ticks[0]
    x0 = exit_ticks[-1]
    entry_bid, entry_ask = float(e0["bid"]), float(e0["ask"])
    exit_bid, exit_ask = float(x0["bid"]), float(x0["ask"])
    entry_spread = entry_ask - entry_bid
    exit_spread = exit_ask - exit_bid

    if action == "BUY":
        entry_fill = entry_ask
        exit_fill = exit_bid
        gross_pnl = exit_fill - entry_fill
    else:
        entry_fill = entry_bid
        exit_fill = exit_ask
        gross_pnl = entry_fill - exit_fill

    # MFE/MAE along path after entry, mark-to-market at executable exit side
    entry_ms = int(e0["epoch_ms"])
    mfe = 0.0
    mae = 0.0
    for t in path:
        if int(t["epoch_ms"]) < entry_ms:
            continue
        if action == "BUY":
            pnl_now = float(t["bid"]) - entry_fill
        else:
            pnl_now = entry_fill - float(t["ask"])
        mfe = max(mfe, pnl_now)
        mae = min(mae, pnl_now)

    risk = float(atr)
    gross_r = gross_pnl / risk

    # Base OBSERVED net = gross (spread embedded; commission/slippage UNKNOWN)
    base = apply_scenario_costs(
        gross_pnl=gross_pnl,
        risk_amount=risk,
        entry_spread=entry_spread,
        exit_spread=exit_spread,
        scenario=COST_SCENARIO_REGISTRY["OBSERVED_BIDASK_ONLY"],
    )

    scenario_nets = {}
    for sid, sc in COST_SCENARIO_REGISTRY.items():
        scenario_nets[sid] = apply_scenario_costs(
            gross_pnl=gross_pnl,
            risk_amount=risk,
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            scenario=sc,
        )

    row: dict[str, Any] = {
        "recipe_id": RECIPE_ID,
        "symbol": SYMBOL,
        "day": day,
        "decision_bar": decision_bar,
        "entry_bar": entry_bar,
        "exit_bar": exit_bar,
        "horizon_bars": horizon_bars,
        "entry_timestamp": e0["timestamp_utc"],
        "exit_timestamp": x0["timestamp_utc"],
        "action": action,
        "entry_bid": entry_bid,
        "entry_ask": entry_ask,
        "exit_bid": exit_bid,
        "exit_ask": exit_ask,
        "entry_fill": entry_fill,
        "exit_fill": exit_fill,
        "gross_pnl": gross_pnl,
        "risk_amount": risk,
        "gross_r": gross_r,
        "spread_cost_embedded": entry_spread + exit_spread,
        "entry_spread": entry_spread,
        "exit_spread": exit_spread,
        "commission": None,  # UNKNOWN under OBSERVED
        "slippage": None,  # UNKNOWN under OBSERVED
        "net_pnl": base["net_pnl"],
        "net_r": base["net_r"],
        "mfe": mfe,
        "mae": mae,
        "mfe_r": mfe / risk,
        "mae_r": mae / risk,
        "exit_reason": "HORIZON_EXIT",
        "data_quality_status": "OK",
        "unknown_cost_components": base["unknown_cost_components"],
        "scenario_nets": scenario_nets,
        "mid_price_used": False,
    }
    row["outcome_sha256"] = _row_hash(row)
    return row


def build_wait_at_decision(
    *,
    day: str,
    decision_idx: int,
    m5: list[dict[str, Any]],
    atr_period: int = ATR_PERIOD,
    horizon_bars: int = HORIZON_BARS,
) -> dict[str, Any]:
    decision_bar = str(m5[decision_idx]["timestamp_utc"])
    entry_idx = decision_idx + 1
    exit_idx = entry_idx + horizon_bars - 1
    atr = atr_at_bar(m5, decision_idx, atr_period)
    dq = "OK" if atr and atr > MIN_ATR else "INVALID_RISK"
    return _wait_outcome(
        day=day,
        decision_bar=decision_bar,
        entry_bar=str(m5[entry_idx]["timestamp_utc"]) if entry_idx < len(m5) else None,
        exit_bar=str(m5[exit_idx]["timestamp_utc"]) if exit_idx < len(m5) else None,
        risk_amount=atr,
        dq=dq,
    )


def build_day_outcomes(
    *,
    day: str,
    m5: list[dict[str, Any]],
    ticks_by_bar: dict[str, list[dict[str, Any]]],
    actions: tuple[str, ...] = ("BUY", "SELL", "WAIT"),
    stride: int = 1,
) -> list[dict[str, Any]]:
    """All eligible decision bars for requested actions (counterfactual per action)."""
    rows: list[dict[str, Any]] = []
    # Need ATR warm-up and full horizon after entry
    first = ATR_PERIOD
    last = len(m5) - (1 + HORIZON_BARS)
    if last < first:
        return rows
    for i in range(first, last + 1, max(1, stride)):
        for action in actions:
            if action == "WAIT":
                rows.append(build_wait_at_decision(day=day, decision_idx=i, m5=m5))
            else:
                rows.append(
                    build_directional_outcome(
                        action=action,
                        day=day,
                        decision_idx=i,
                        m5=m5,
                        ticks_by_bar=ticks_by_bar,
                    )
                )
    return rows
