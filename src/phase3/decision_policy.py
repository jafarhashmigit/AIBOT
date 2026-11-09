"""Deterministic BUY / SELL / WAIT policy interface."""

from __future__ import annotations

import numpy as np

from phase3.constants import DEFAULT_MIN_GAP, MIN_INNER_TRADES, THRESHOLD_SELECTION_RULE
from phase3.nplib import col


def decision(ev_buy: float, ev_sell: float, tau: float, min_gap: float) -> str:
    if not np.isfinite(ev_buy) or not np.isfinite(ev_sell):
        return "WAIT"
    if abs(ev_buy - ev_sell) < min_gap:
        return "WAIT"
    if ev_buy > ev_sell and ev_buy > tau:
        return "BUY"
    if ev_sell > ev_buy and ev_sell > tau:
        return "SELL"
    return "WAIT"


def decide_batch(ev_buy: np.ndarray, ev_sell: np.ndarray, tau: float,
                 min_gap: float) -> np.ndarray:
    buy = np.asarray(ev_buy, dtype=float)
    sell = np.asarray(ev_sell, dtype=float)
    out = np.full(len(buy), "WAIT", dtype=object)
    finite = np.isfinite(buy) & np.isfinite(sell)
    gap = np.abs(buy - sell) >= min_gap
    out[finite & gap & (buy > sell) & (buy > tau)] = "BUY"
    out[finite & gap & (sell > buy) & (sell > tau)] = "SELL"
    return out


def block_reason(ev_buy: float, ev_sell: float, tau: float, min_gap: float, action: str) -> str:
    if action != "WAIT":
        return ""
    if not np.isfinite(ev_buy) or not np.isfinite(ev_sell):
        return "non_finite_evidence"
    if abs(ev_buy - ev_sell) < min_gap:
        return "sides_too_close"
    if max(ev_buy, ev_sell) <= tau:
        return "insufficient_ev"
    return "no_side_clears_rule"


def realized_from_action(rows: list[dict], actions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r = np.zeros(len(rows), dtype=float)
    pnl = np.zeros(len(rows), dtype=float)
    reason = np.array([""] * len(rows), dtype=object)
    buy_r = col(rows, "actual_net_r_BUY")
    sell_r = col(rows, "actual_net_r_SELL")
    buy_pnl = col(rows, "actual_net_pnl_BUY")
    sell_pnl = col(rows, "actual_net_pnl_SELL")
    buy_ex = col(rows, "actual_exit_reason_BUY", dtype=object)
    sell_ex = col(rows, "actual_exit_reason_SELL", dtype=object)
    take_buy = actions == "BUY"
    take_sell = actions == "SELL"
    r[take_buy] = buy_r[take_buy]
    r[take_sell] = sell_r[take_sell]
    pnl[take_buy] = buy_pnl[take_buy]
    pnl[take_sell] = sell_pnl[take_sell]
    reason[take_buy] = buy_ex[take_buy]
    reason[take_sell] = sell_ex[take_sell]
    return r, pnl, reason


def mean_trade_r(rows: list[dict], actions: np.ndarray) -> dict:
    executed = actions != "WAIT"
    n = int(executed.sum())
    if n == 0:
        return {"n_trades": 0, "mean_trade_r": float("nan"), "n_buy": 0, "n_sell": 0,
                "n_wait": int((actions == "WAIT").sum())}
    r, _, _ = realized_from_action(rows, actions)
    return {
        "n_trades": n,
        "mean_trade_r": float(r[executed].mean()),
        "n_buy": int((actions == "BUY").sum()),
        "n_sell": int((actions == "SELL").sum()),
        "n_wait": int((actions == "WAIT").sum()),
    }


def select_threshold(inner: list[dict], ev_buy: np.ndarray, ev_sell: np.ndarray,
                     candidates: tuple[float, ...], min_gap: float = DEFAULT_MIN_GAP,
                     min_trades: int = MIN_INNER_TRADES) -> dict:
    rows = []
    positive = []
    for tau in candidates:
        actions = decide_batch(ev_buy, ev_sell, tau, min_gap)
        stats = mean_trade_r(inner, actions)
        stats["tau"] = float(tau)
        rows.append(stats)
        if stats["n_trades"] >= min_trades and stats["mean_trade_r"] > 0:
            positive.append(float(tau))
    if positive:
        chosen = max(positive)
        status = "positive_conservative"
    else:
        chosen = None
        status = "fallback_wait"
    return {
        "tau": chosen,
        "status": status,
        "fallback_wait": chosen is None,
        "min_gap": min_gap,
        "min_trades": min_trades,
        "selection_rule": THRESHOLD_SELECTION_RULE["id"],
        "candidates": rows,
    }
