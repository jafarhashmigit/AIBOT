"""Deterministic paper execution — historical/replay bid/ask only. No broker orders."""

from __future__ import annotations

import uuid
from typing import Any

from phase54.timeutil import dual_stamp, now_utc_iso


class PaperExecutionError(ValueError):
    pass


def _first_tick(ticks_by_bar: dict[str, list], bar_ts: str) -> dict[str, Any]:
    ticks = ticks_by_bar.get(bar_ts) or []
    if not ticks:
        raise PaperExecutionError(f"incomplete_entry_path:{bar_ts}")
    t = ticks[0]
    if t.get("bid") is None or t.get("ask") is None or float(t["ask"]) < float(t["bid"]):
        raise PaperExecutionError("invalid_entry_tick")
    return t


def _last_tick(ticks_by_bar: dict[str, list], bar_ts: str) -> dict[str, Any]:
    ticks = ticks_by_bar.get(bar_ts) or []
    if not ticks:
        raise PaperExecutionError(f"incomplete_exit_path:{bar_ts}")
    t = ticks[-1]
    if t.get("bid") is None or t.get("ask") is None or float(t["ask"]) < float(t["bid"]):
        raise PaperExecutionError("invalid_exit_tick")
    return t


def open_paper_position(
    *,
    decision: dict[str, Any],
    market_state: dict[str, Any],
    entry_bar_ts: str,
    ticks_by_bar: dict[str, list],
    sizing: dict[str, Any],
    m5: list[dict[str, Any]],
    entry_idx: int,
) -> dict[str, Any]:
    action = decision.get("action")
    if action not in ("BUY", "SELL"):
        raise PaperExecutionError("WAIT_cannot_open")
    tick = _first_tick(ticks_by_bar, entry_bar_ts)
    bid, ask = float(tick["bid"]), float(tick["ask"])
    entry = ask if action == "BUY" else bid
    spread = ask - bid  # recorded once at entry
    atr = market_state.get("atr")
    stop_dist = (sizing or {}).get("stop_distance")
    if stop_dist is None or float(stop_dist) <= 0:
        raise PaperExecutionError("invalid_stop")
    if action == "BUY":
        sl = entry - float(stop_dist)
        tp = entry + float(stop_dist)  # optional 1R TP for monitoring
    else:
        sl = entry + float(stop_dist)
        tp = entry - float(stop_dist)

    pos = {
        "position_id": uuid.uuid4().hex,
        "decision_id": decision["decision_id"],
        "observation_id": decision.get("observation_id"),
        "market_state_id": market_state.get("market_state_id"),
        "symbol": market_state.get("symbol"),
        "timeframe": market_state.get("timeframe"),
        "side": action,
        "status": "OPEN",
        "entry_bar": entry_bar_ts,
        "entry_idx": entry_idx,
        "entry_timestamp": tick["timestamp_utc"],
        "timestamps_entry": dual_stamp(tick["timestamp_utc"]),
        "entry_bid": bid,
        "entry_ask": ask,
        "entry_fill": entry,
        "entry_spread": spread,
        "units": float((sizing or {}).get("units") or 0),
        "stop_loss": sl,
        "take_profit": tp,
        "atr_at_entry": atr,
        "commission": None,
        "slippage": None,
        "audit": [
            {
                "event": "PAPER_ENTRY",
                "ts": now_utc_iso(),
                "fill": entry,
                "spread_recorded_once": spread,
            }
        ],
        "created_iso": now_utc_iso(),
    }
    return pos


def monitor_and_maybe_exit(
    position: dict[str, Any],
    *,
    m5: list[dict[str, Any]],
    ticks_by_bar: dict[str, list],
    current_idx: int,
    horizon_bars: int,
) -> dict[str, Any] | None:
    """Return exit record if SL/TP/horizon hit; else None. Rejects incomplete paths."""
    if position.get("status") != "OPEN":
        return None
    entry_idx = int(position["entry_idx"])
    side = position["side"]
    sl = float(position["stop_loss"])
    tp = float(position["take_profit"])
    # Scan bars from entry through current
    last = min(current_idx, entry_idx + horizon_bars - 1)
    if last < entry_idx:
        return None
    for j in range(entry_idx, last + 1):
        bar = m5[j]
        bar_ts = str(bar["timestamp_utc"])
        ticks = ticks_by_bar.get(bar_ts) or []
        if not ticks:
            raise PaperExecutionError(f"missing_path_ticks:{bar_ts}")
        for t in ticks:
            bid, ask = float(t["bid"]), float(t["ask"])
            if side == "BUY":
                # exit at bid
                if bid <= sl:
                    return _close(position, t, bid, "STOP_LOSS", bar_ts, j)
                if bid >= tp:
                    return _close(position, t, bid, "TAKE_PROFIT", bar_ts, j)
            else:
                if ask >= sl:
                    return _close(position, t, ask, "STOP_LOSS", bar_ts, j)
                if ask <= tp:
                    return _close(position, t, ask, "TAKE_PROFIT", bar_ts, j)
        if j == entry_idx + horizon_bars - 1:
            t = ticks[-1]
            fill = float(t["bid"]) if side == "BUY" else float(t["ask"])
            return _close(position, t, fill, "HORIZON_EXIT", bar_ts, j)
    return None


def _close(
    position: dict[str, Any],
    tick: dict[str, Any],
    fill: float,
    reason: str,
    bar_ts: str,
    exit_idx: int,
) -> dict[str, Any]:
    bid, ask = float(tick["bid"]), float(tick["ask"])
    exit_spread = ask - bid
    entry = float(position["entry_fill"])
    side = position["side"]
    if side == "BUY":
        gross = fill - entry
    else:
        gross = entry - fill
    # Spread already embedded in bid/ask fills — do not subtract again
    atr = position.get("atr_at_entry")
    risk = float(atr) if atr and float(atr) > 0 else None
    net_r = (gross / risk) if risk else None
    closed = {
        **position,
        "status": "CLOSED",
        "exit_bar": bar_ts,
        "exit_idx": exit_idx,
        "exit_timestamp": tick["timestamp_utc"],
        "timestamps_exit": dual_stamp(tick["timestamp_utc"]),
        "exit_bid": bid,
        "exit_ask": ask,
        "exit_fill": fill,
        "exit_spread": exit_spread,
        "exit_reason": reason,
        "gross_pnl": gross,
        "net_pnl": gross,  # commission/slippage UNKNOWN — not invented
        "net_r": net_r,
        "commission": None,
        "slippage": None,
        "closed_iso": now_utc_iso(),
    }
    closed["audit"] = list(position.get("audit") or []) + [
        {"event": "PAPER_EXIT", "ts": now_utc_iso(), "fill": fill, "reason": reason, "net_r": net_r}
    ]
    return closed


def force_horizon_exit_from_bars(
    position: dict[str, Any],
    *,
    m5: list[dict[str, Any]],
    ticks_by_bar: dict[str, list],
    horizon_bars: int,
) -> dict[str, Any]:
    entry_idx = int(position["entry_idx"])
    exit_idx = entry_idx + horizon_bars - 1
    if exit_idx >= len(m5):
        raise PaperExecutionError("incomplete_horizon")
    bar_ts = str(m5[exit_idx]["timestamp_utc"])
    t = _last_tick(ticks_by_bar, bar_ts)
    fill = float(t["bid"]) if position["side"] == "BUY" else float(t["ask"])
    return _close(position, t, fill, "HORIZON_EXIT", bar_ts, exit_idx)
