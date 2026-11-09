"""Synthetic decision-time pairs. No holdout. No post-cutoff stamps."""

from __future__ import annotations

from datetime import datetime, timedelta

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def stamps(n: int, start: str = "2026-06-19 10:00:00", step_minutes: int = 5) -> list[str]:
    t = datetime.strptime(start, TIME_FORMAT)
    return [(t + timedelta(minutes=step_minutes * i)).strftime(TIME_FORMAT) for i in range(n)]


def pair(timestamp: str, fold_id: str = "WF1", *, buy_r: float = 0.1, sell_r: float = -0.05) -> dict:
    p_tp_buy = 0.40
    p_tp_sell = 0.30
    return {
        "timestamp": timestamp,
        "fold_id": fold_id,
        "buy": {
            "p_tp_rf": p_tp_buy,
            "p_sl_rf": 0.30,
            "p_time_rf": 0.30,
            "pred_r_rf": buy_r,
            "pred_r_ridge": buy_r * 0.8,
        },
        "sell": {
            "p_tp_rf": p_tp_sell,
            "p_sl_rf": 0.40,
            "p_time_rf": 0.30,
            "pred_r_rf": sell_r,
            "pred_r_ridge": sell_r * 0.8,
        },
    }


def eval_row(timestamp: str, fold_id: str = "WF1", *, buy: float = -1.0, sell: float = 0.5) -> dict:
    return {
        "timestamp": timestamp,
        "fold_id": fold_id,
        "actual_exit_reason_BUY": "SL",
        "actual_net_r_BUY": buy,
        "actual_net_pnl_BUY": buy * 2.0,
        "actual_exit_reason_SELL": "TP",
        "actual_net_r_SELL": sell,
        "actual_net_pnl_SELL": sell * 2.0,
    }


def series(n: int = 20) -> tuple[list[dict], list[dict]]:
    times = stamps(n)
    pairs = [pair(t) for t in times]
    rows = [eval_row(t) for t in times]
    return pairs, rows
