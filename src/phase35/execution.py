"""Bid/ask-aware execution + legacy cost views. No midpoint fills when bid/ask exist."""

from __future__ import annotations

from typing import Any

from phase35.candles import bar_window_complete
from phase35.constants import (
    EXTRA_COST_PER_SIDE_FROZEN,
    HORIZON_BARS,
    MIN_SPREAD_POINTS_FROZEN,
    POINT_SIZE,
    SL_MULT,
    TP_MULT,
)


def _legacy_spread_usd(spread_open: float) -> float:
    return max(float(spread_open), MIN_SPREAD_POINTS_FROZEN * POINT_SIZE)


def simulate_bidask_trade(
    *,
    side: str,
    signal_idx: int,
    times: list[str],
    by_time: dict[str, dict],
    ticks_by_bar: dict[str, list[dict]],
    atr: float,
) -> dict[str, Any]:
    """Entry next bar open on executable side; TP/SL via chronological tick path."""
    entry_idx = signal_idx + 1
    last_idx = entry_idx + HORIZON_BARS - 1
    if last_idx >= len(times):
        return {"status": "UNRESOLVED_DATA_GAP", "reason": "incomplete_horizon_end"}
    if not bar_window_complete(times, entry_idx, HORIZON_BARS, by_time):
        return {"status": "UNRESOLVED_DATA_GAP", "reason": "missing_or_noncontiguous_bars"}

    entry_bar = times[entry_idx]
    entry_ticks = ticks_by_bar.get(entry_bar) or []
    if not entry_ticks:
        return {"status": "UNRESOLVED_DATA_GAP", "reason": "empty_entry_bar_ticks"}

    if side == "BUY":
        entry = float(entry_ticks[0]["ask"])
        tp = entry + TP_MULT * atr
        sl = entry - SL_MULT * atr
    else:
        entry = float(entry_ticks[0]["bid"])
        tp = entry - TP_MULT * atr
        sl = entry + SL_MULT * atr

    # Walk ticks in chronological order across horizon bars
    path_ticks: list[dict] = []
    for i in range(entry_idx, last_idx + 1):
        bt = times[i]
        bar_ticks = ticks_by_bar.get(bt) or []
        if not bar_ticks and i == entry_idx:
            return {"status": "UNRESOLVED_DATA_GAP", "reason": "no_ticks_in_window"}
        # Missing ticks in a later bar while candle exists is still a gap for path certainty
        if not bar_ticks:
            return {"status": "UNRESOLVED_DATA_GAP", "reason": f"no_ticks_in_bar_{bt}"}
        path_ticks.extend(bar_ticks)

    exit_px = None
    exit_reason = None
    exit_time = None
    for t in path_ticks:
        # Skip ticks before entry tick
        if int(t["epoch_ms"]) < int(entry_ticks[0]["epoch_ms"]):
            continue
        bid = float(t["bid"])
        ask = float(t["ask"])
        if side == "BUY":
            # Exit at bid
            if bid <= sl:
                exit_px, exit_reason, exit_time = bid, "FAIL", t["timestamp_utc"]
                break
            if bid >= tp:
                exit_px, exit_reason, exit_time = bid, "PASS", t["timestamp_utc"]
                break
        else:
            # Exit at ask
            if ask >= sl:
                exit_px, exit_reason, exit_time = ask, "FAIL", t["timestamp_utc"]
                break
            if ask <= tp:
                exit_px, exit_reason, exit_time = ask, "PASS", t["timestamp_utc"]
                break

    if exit_px is None:
        # TIMEOUT at last tick executable side
        last = path_ticks[-1]
        exit_px = float(last["bid"]) if side == "BUY" else float(last["ask"])
        exit_reason = "TIMEOUT"
        exit_time = last["timestamp_utc"]

    if side == "BUY":
        pnl = exit_px - entry
    else:
        pnl = entry - exit_px
    risk = SL_MULT * atr
    if risk <= 0:
        return {"status": "UNRESOLVED_DATA_GAP", "reason": "invalid_atr_risk"}
    net_r = pnl / risk
    # Spread cost embedded in bid/ask fills — do not add frozen extra
    return {
        "status": exit_reason,
        "side": side,
        "entry_fill": entry,
        "exit_fill": exit_px,
        "exit_reason": exit_reason,
        "entry_time": entry_ticks[0]["timestamp_utc"],
        "exit_time": exit_time,
        "tp": tp,
        "sl": sl,
        "atr": atr,
        "initial_risk": risk,
        "net_pnl": pnl,
        "net_r": net_r,
        "costs": abs(entry - (float(entry_ticks[0]["bid"]) if side == "BUY" else float(entry_ticks[0]["ask"]))),
        "model": "HISTORICAL_BIDASK",
        "commission": "COMMISSION_UNVERIFIED",
        "slippage": "SLIPPAGE_UNVERIFIED",
        "extra_cost_added": 0.0,
    }


def simulate_legacy_trade(
    *,
    side: str,
    signal_idx: int,
    times: list[str],
    by_time: dict[str, dict],
    atr: float,
) -> dict[str, Any]:
    """VIEW B — frozen mid+floor+extra model (comparison only). Same-bar SL before TP."""
    entry_idx = signal_idx + 1
    last_idx = entry_idx + HORIZON_BARS - 1
    if last_idx >= len(times) or not bar_window_complete(times, entry_idx, HORIZON_BARS, by_time):
        return {"status": "UNRESOLVED_DATA_GAP", "reason": "incomplete_window"}

    ebar = by_time[times[entry_idx]]
    spr = _legacy_spread_usd(float(ebar["spread_open"]))
    mid_open = float(ebar["open"])
    if side == "BUY":
        entry = mid_open + spr + EXTRA_COST_PER_SIDE_FROZEN
        tp = entry + TP_MULT * atr
        sl = entry - SL_MULT * atr
    else:
        entry = mid_open - EXTRA_COST_PER_SIDE_FROZEN
        tp = entry - TP_MULT * atr
        sl = entry + SL_MULT * atr

    exit_px = None
    exit_reason = None
    exit_time = None
    for i in range(entry_idx, last_idx + 1):
        b = by_time[times[i]]
        hi = float(b["high"])
        lo = float(b["low"])
        spr_i = _legacy_spread_usd(float(b["spread_open"]))
        if side == "BUY":
            # exit on bid ≈ mid - extra; use high/low mid as proxy with -extra
            bid_hi = hi - EXTRA_COST_PER_SIDE_FROZEN
            bid_lo = lo - EXTRA_COST_PER_SIDE_FROZEN
            hit_sl = bid_lo <= sl
            hit_tp = bid_hi >= tp
            if hit_sl and hit_tp:
                exit_px, exit_reason = sl, "FAIL"  # conservative SL first
                exit_time = times[i]
                break
            if hit_sl:
                exit_px, exit_reason, exit_time = sl, "FAIL", times[i]
                break
            if hit_tp:
                exit_px, exit_reason, exit_time = tp, "PASS", times[i]
                break
        else:
            ask_lo = lo + spr_i + EXTRA_COST_PER_SIDE_FROZEN
            ask_hi = hi + spr_i + EXTRA_COST_PER_SIDE_FROZEN
            hit_sl = ask_hi >= sl
            hit_tp = ask_lo <= tp
            if hit_sl and hit_tp:
                exit_px, exit_reason, exit_time = sl, "FAIL", times[i]
                break
            if hit_sl:
                exit_px, exit_reason, exit_time = sl, "FAIL", times[i]
                break
            if hit_tp:
                exit_px, exit_reason, exit_time = tp, "PASS", times[i]
                break

    if exit_px is None:
        last = by_time[times[last_idx]]
        if side == "BUY":
            exit_px = float(last["close"]) - EXTRA_COST_PER_SIDE_FROZEN
        else:
            exit_px = float(last["close"]) + _legacy_spread_usd(float(last["spread_open"])) + EXTRA_COST_PER_SIDE_FROZEN
        exit_reason = "TIMEOUT"
        exit_time = times[last_idx]

    pnl = (exit_px - entry) if side == "BUY" else (entry - exit_px)
    risk = SL_MULT * atr
    return {
        "status": exit_reason,
        "side": side,
        "entry_fill": entry,
        "exit_fill": exit_px,
        "exit_reason": exit_reason,
        "entry_time": times[entry_idx],
        "exit_time": exit_time,
        "tp": tp,
        "sl": sl,
        "atr": atr,
        "initial_risk": risk,
        "net_pnl": pnl,
        "net_r": pnl / risk if risk > 0 else 0.0,
        "costs": spr + 2 * EXTRA_COST_PER_SIDE_FROZEN if side == "BUY" else (spr + 2 * EXTRA_COST_PER_SIDE_FROZEN),
        "model": "LEGACY_FROZEN",
        "note": "M5 mid OHLC barrier path — NOT tick-path truth; comparison only",
    }


def simulate_stress_trade(bidask_result: dict[str, Any], *, extra_per_side: float = 0.05) -> dict[str, Any]:
    """VIEW C — sensitivity only: subtract unverified extra friction from bid/ask R."""
    if bidask_result.get("status") in {None, "UNRESOLVED_DATA_GAP"} or "net_r" not in bidask_result:
        return {**bidask_result, "model": "STRESS", "status": bidask_result.get("status", "UNRESOLVED_DATA_GAP")}
    risk = float(bidask_result["initial_risk"])
    extra = 2 * extra_per_side
    pnl = float(bidask_result["net_pnl"]) - extra
    out = dict(bidask_result)
    out.update(
        {
            "model": "STRESS",
            "net_pnl": pnl,
            "net_r": pnl / risk if risk > 0 else 0.0,
            "extra_cost_added": extra,
            "stress_assumption": f"unverified extra ${extra_per_side}/side subtracted; COMMISSION_UNVERIFIED; SLIPPAGE_UNVERIFIED",
        }
    )
    return out
