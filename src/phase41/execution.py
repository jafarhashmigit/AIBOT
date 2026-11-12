"""Deterministic bid/ask execution reality engine (Phase41)."""

from __future__ import annotations

from typing import Any

from phase41.constants import HORIZON_BARS, SL_MULT, TP_MULT


def simulate_trade(
    *,
    side: str,
    signal_idx: int,
    times: list[str],
    ticks_by_bar: dict[str, list[dict]],
    atr: float,
    adverse_ambiguous: bool = True,
) -> dict[str, Any]:
    """BUY entry ASK / exit BID; SELL entry BID / exit ASK. Tick-path TP/SL."""
    entry_idx = signal_idx + 1
    last_idx = entry_idx + HORIZON_BARS - 1
    if entry_idx >= len(times) or last_idx >= len(times):
        return {"status": "INSUFFICIENT_TICK_COVERAGE", "reason": "incomplete_horizon_bars"}

    horizon_bars = times[entry_idx : last_idx + 1]
    missing = [t for t in horizon_bars if not ticks_by_bar.get(t)]
    if missing:
        return {
            "status": "INSUFFICIENT_TICK_COVERAGE",
            "reason": "missing_ticks_in_holding_path",
            "missing_bars": missing[:12],
            "n_missing_bars": len(missing),
        }

    entry_bar = times[entry_idx]
    entry_ticks = sorted(ticks_by_bar[entry_bar], key=lambda t: int(t["epoch_ms"]))
    if side == "BUY":
        entry = float(entry_ticks[0]["ask"])
        tp = entry + TP_MULT * atr
        sl = entry - SL_MULT * atr
    else:
        entry = float(entry_ticks[0]["bid"])
        tp = entry - TP_MULT * atr
        sl = entry + SL_MULT * atr
    entry_spread = float(entry_ticks[0]["ask"]) - float(entry_ticks[0]["bid"])

    path: list[dict] = []
    for bt in horizon_bars:
        path.extend(sorted(ticks_by_bar[bt], key=lambda t: int(t["epoch_ms"])))

    entry_ms = int(entry_ticks[0]["epoch_ms"])
    exit_px = None
    exit_reason = None
    exit_time = None
    exit_spread = None
    mae = 0.0
    mfe = 0.0
    uncertain = False
    uncertain_reason = None

    for t in path:
        if int(t["epoch_ms"]) < entry_ms:
            continue
        bid = float(t["bid"])
        ask = float(t["ask"])
        if side == "BUY":
            pnl_now = bid - entry
            mae = min(mae, pnl_now)
            mfe = max(mfe, pnl_now)
            hit_sl = bid <= sl
            hit_tp = bid >= tp
            if hit_sl and hit_tp:
                uncertain = True
                uncertain_reason = "both_barriers_same_tick"
                exit_px = bid
                exit_reason = "FAIL" if adverse_ambiguous else "PASS"
                exit_time = t["timestamp_utc"]
                exit_spread = ask - bid
                break
            if hit_sl:
                exit_px, exit_reason, exit_time = bid, "FAIL", t["timestamp_utc"]
                exit_spread = ask - bid
                break
            if hit_tp:
                exit_px, exit_reason, exit_time = bid, "PASS", t["timestamp_utc"]
                exit_spread = ask - bid
                break
        else:
            pnl_now = entry - ask
            mae = min(mae, pnl_now)
            mfe = max(mfe, pnl_now)
            hit_sl = ask >= sl
            hit_tp = ask <= tp
            if hit_sl and hit_tp:
                uncertain = True
                uncertain_reason = "both_barriers_same_tick"
                exit_px = ask
                exit_reason = "FAIL" if adverse_ambiguous else "PASS"
                exit_time = t["timestamp_utc"]
                exit_spread = ask - bid
                break
            if hit_sl:
                exit_px, exit_reason, exit_time = ask, "FAIL", t["timestamp_utc"]
                exit_spread = ask - bid
                break
            if hit_tp:
                exit_px, exit_reason, exit_time = ask, "PASS", t["timestamp_utc"]
                exit_spread = ask - bid
                break

    if exit_px is None:
        last = path[-1]
        exit_px = float(last["bid"]) if side == "BUY" else float(last["ask"])
        exit_reason = "TIMEOUT"
        exit_time = last["timestamp_utc"]
        exit_spread = float(last["ask"]) - float(last["bid"])

    gross_pnl = (exit_px - entry) if side == "BUY" else (entry - exit_px)
    risk = SL_MULT * atr
    if risk <= 0:
        return {"status": "EXECUTION_UNCERTAIN", "reason": "invalid_atr_risk"}

    net_pnl = gross_pnl  # spread embedded in bid/ask; do not double-count
    net_r = net_pnl / risk
    hold_ms = None
    if exit_time is not None:
        # approximate from exit tick search
        for t in path:
            if t["timestamp_utc"] == exit_time:
                hold_ms = int(t["epoch_ms"]) - entry_ms
                break

    status = "EXECUTION_UNCERTAIN" if uncertain else exit_reason
    return {
        "status": status,
        "exit_reason": exit_reason,
        "side": side,
        "entry_fill": entry,
        "exit_fill": exit_px,
        "entry_time": entry_ticks[0]["timestamp_utc"],
        "exit_time": exit_time,
        "entry_bar": entry_bar,
        "tp": tp,
        "sl": sl,
        "atr": atr,
        "initial_risk": risk,
        "entry_spread": entry_spread,
        "exit_spread": exit_spread,
        "gross_pnl": gross_pnl,
        "spread_cost_embedded_in_bidask": True,
        "commission": 0.0,
        "slippage_modeled": 0.0,
        "net_pnl": net_pnl,
        "net_r": net_r,
        "mae": mae,
        "mfe": mfe,
        "mae_r": mae / risk,
        "mfe_r": mfe / risk,
        "hold_ms": hold_ms,
        "uncertain": uncertain,
        "uncertain_reason": uncertain_reason,
        "adverse_assumption_applied": bool(uncertain and adverse_ambiguous),
        "n_path_ticks": len(path),
    }


def apply_cost_scenario(
    trade: dict[str, Any],
    *,
    slippage_per_side: float,
    commission_per_side: float,
    spread_widen_mult: float,
) -> dict[str, Any]:
    """Hypothetical extra costs on top of observed bid/ask (not live broker evidence)."""
    if trade.get("net_r") is None or trade.get("initial_risk") in (None, 0):
        return {**trade, "scenario_net_r": None}
    risk = float(trade["initial_risk"])
    base_spread = float(trade.get("entry_spread") or 0) + float(trade.get("exit_spread") or 0)
    extra_spread = base_spread * (spread_widen_mult - 1.0)
    extra = 2.0 * slippage_per_side + 2.0 * commission_per_side + extra_spread
    net_pnl = float(trade["net_pnl"]) - extra
    return {
        **trade,
        "scenario_extra_cost_usd": extra,
        "scenario_net_pnl": net_pnl,
        "scenario_net_r": net_pnl / risk,
        "scenario_params": {
            "slippage_per_side": slippage_per_side,
            "commission_per_side": commission_per_side,
            "spread_widen_mult": spread_widen_mult,
            "note": "hypothetical stress; not observed live costs; MetaQuotes-Demo ≠ live broker",
        },
    }
