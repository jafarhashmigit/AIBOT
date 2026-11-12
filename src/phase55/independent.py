"""Independent bid/ask PnL/R recomputation — does not call the execution engine."""

from __future__ import annotations

from typing import Any


def recompute_from_ticks(
    *,
    side: str,
    entry_ticks: list[dict[str, Any]],
    exit_ticks: list[dict[str, Any]],
    atr: float | None,
    stop_distance: float | None = None,
) -> dict[str, Any]:
    """Simple first/last tick recompute (horizon-style). Prefer recompute_path for SL/TP."""
    if side not in ("BUY", "SELL"):
        return {"ok": False, "error": "bad_side"}
    if not entry_ticks or not exit_ticks:
        return {"ok": False, "error": "missing_ticks"}
    e0, x0 = entry_ticks[0], exit_ticks[-1]
    eb, ea = float(e0["bid"]), float(e0["ask"])
    xb, xa = float(x0["bid"]), float(x0["ask"])
    if ea < eb or xa < xb:
        return {"ok": False, "error": "crossed"}
    if side == "BUY":
        entry_fill, exit_fill = ea, xb
        gross = exit_fill - entry_fill
    else:
        entry_fill, exit_fill = eb, xa
        gross = entry_fill - exit_fill
    return {
        "ok": True,
        "side": side,
        "entry_bid": eb,
        "entry_ask": ea,
        "exit_bid": xb,
        "exit_ask": xa,
        "entry_fill": entry_fill,
        "exit_fill": exit_fill,
        "entry_spread": ea - eb,
        "gross_pnl": gross,
        "net_pnl": gross,
        "net_r": (gross / float(atr)) if atr and float(atr) > 0 else None,
        "exit_reason": "HORIZON_ASSUMED",
        "commission": None,
        "slippage": None,
    }


def recompute_path(
    *,
    side: str,
    m5: list[dict[str, Any]],
    ticks_by_bar: dict[str, list],
    entry_idx: int,
    horizon_bars: int,
    atr: float | None,
    stop_distance: float,
) -> dict[str, Any]:
    """
    Independent path walk mirroring paper monitoring rules without importing paper_exec.
    BUY: entry first ASK; exit BID on SL/TP/horizon.
    SELL: entry first BID; exit ASK on SL/TP/horizon.
    """
    if side not in ("BUY", "SELL"):
        return {"ok": False, "error": "bad_side"}
    if entry_idx < 0 or entry_idx >= len(m5):
        return {"ok": False, "error": "bad_entry_idx"}
    entry_bar = str(m5[entry_idx]["timestamp_utc"])
    eticks = ticks_by_bar.get(entry_bar) or []
    if not eticks:
        return {"ok": False, "error": "missing_entry_ticks"}
    e0 = eticks[0]
    eb, ea = float(e0["bid"]), float(e0["ask"])
    if ea < eb:
        return {"ok": False, "error": "crossed_entry"}
    entry_fill = ea if side == "BUY" else eb
    sd = float(stop_distance)
    if sd <= 0:
        return {"ok": False, "error": "invalid_stop"}
    if side == "BUY":
        sl, tp = entry_fill - sd, entry_fill + sd
    else:
        sl, tp = entry_fill + sd, entry_fill - sd

    last = entry_idx + horizon_bars - 1
    if last >= len(m5):
        return {"ok": False, "error": "incomplete_horizon"}

    for j in range(entry_idx, last + 1):
        bar_ts = str(m5[j]["timestamp_utc"])
        ticks = ticks_by_bar.get(bar_ts) or []
        if not ticks:
            return {"ok": False, "error": f"missing_path_ticks:{bar_ts}"}
        for t in ticks:
            bid, ask = float(t["bid"]), float(t["ask"])
            if side == "BUY":
                if bid <= sl:
                    return _pack(side, eb, ea, bid, ask, entry_fill, bid, atr, "STOP_LOSS", j)
                if bid >= tp:
                    return _pack(side, eb, ea, bid, ask, entry_fill, bid, atr, "TAKE_PROFIT", j)
            else:
                if ask >= sl:
                    return _pack(side, eb, ea, bid, ask, entry_fill, ask, atr, "STOP_LOSS", j)
                if ask <= tp:
                    return _pack(side, eb, ea, bid, ask, entry_fill, ask, atr, "TAKE_PROFIT", j)
        if j == last:
            t = ticks[-1]
            bid, ask = float(t["bid"]), float(t["ask"])
            fill = bid if side == "BUY" else ask
            return _pack(side, eb, ea, bid, ask, entry_fill, fill, atr, "HORIZON_EXIT", j)
    return {"ok": False, "error": "no_exit"}


def _pack(side, eb, ea, xb, xa, entry_fill, exit_fill, atr, reason, exit_idx) -> dict[str, Any]:
    if side == "BUY":
        gross = exit_fill - entry_fill
    else:
        gross = entry_fill - exit_fill
    return {
        "ok": True,
        "side": side,
        "entry_bid": eb,
        "entry_ask": ea,
        "exit_bid": xb,
        "exit_ask": xa,
        "entry_fill": entry_fill,
        "exit_fill": exit_fill,
        "entry_spread": ea - eb,
        "gross_pnl": gross,
        "net_pnl": gross,
        "net_r": (gross / float(atr)) if atr and float(atr) > 0 else None,
        "exit_reason": reason,
        "exit_idx": exit_idx,
        "commission": None,
        "slippage": None,
    }


def compare_to_engine(engine_closed: dict[str, Any], independent: dict[str, Any], *, tol: float = 1e-9) -> dict[str, Any]:
    mismatches = []
    if not independent.get("ok"):
        return {"ok": False, "mismatches": ["independent_failed:" + str(independent.get("error"))], "independent": independent}
    pairs = [
        ("entry_fill", "entry_fill"),
        ("exit_fill", "exit_fill"),
        ("entry_bid", "entry_bid"),
        ("entry_ask", "entry_ask"),
        ("exit_bid", "exit_bid"),
        ("exit_ask", "exit_ask"),
        ("gross_pnl", "gross_pnl"),
        ("net_r", "net_r"),
        ("exit_reason", "exit_reason"),
    ]
    for ek, ik in pairs:
        ev, iv = engine_closed.get(ek), independent.get(ik)
        if ek == "exit_reason":
            if str(ev) != str(iv):
                mismatches.append(f"{ek}:engine={ev},indep={iv}")
            continue
        if ev is None or iv is None:
            if ev != iv:
                mismatches.append(f"{ek}:engine={ev},indep={iv}")
            continue
        if abs(float(ev) - float(iv)) > tol:
            mismatches.append(f"{ek}:engine={ev},indep={iv}")
    side = engine_closed.get("side")
    if side == "BUY":
        if abs(float(engine_closed["entry_fill"]) - float(engine_closed["entry_ask"])) > tol:
            mismatches.append("BUY_entry_not_ask")
        if abs(float(engine_closed["exit_fill"]) - float(engine_closed["exit_bid"])) > tol:
            mismatches.append("BUY_exit_not_bid")
    if side == "SELL":
        if abs(float(engine_closed["entry_fill"]) - float(engine_closed["entry_bid"])) > tol:
            mismatches.append("SELL_entry_not_bid")
        if abs(float(engine_closed["exit_fill"]) - float(engine_closed["exit_ask"])) > tol:
            mismatches.append("SELL_exit_not_ask")
    return {"ok": len(mismatches) == 0, "mismatches": mismatches, "independent": independent}
