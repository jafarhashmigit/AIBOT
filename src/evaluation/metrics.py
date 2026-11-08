"""Trade-performance metrics.

Net R, profit factor and closed-trade drawdown match backtest_rf_m5.py /
research_rf_m5_model_comparison.trade_metrics. New names are documented.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research_rf_m5_model_comparison import longest_losing_streak, max_drawdown, profit_factor, trade_metrics


def net_r(net_pnl, sl_distance) -> np.ndarray:
    """R = net P&L / initial SL distance. Same definition as backtest_rf_m5."""
    sl = np.asarray(sl_distance, dtype=float)
    if np.any(~np.isfinite(sl) | (sl <= 0)):
        raise ValueError("SL distance must be finite and positive")
    return np.asarray(net_pnl, dtype=float) / sl


def expectancy(net: np.ndarray) -> float:
    """Mean net P&L per trade (same as average_trade in the EMA reports)."""
    net = np.asarray(net, dtype=float)
    return float(net.mean()) if len(net) else float("nan")


def win_rate(net: np.ndarray) -> float:
    net = np.asarray(net, dtype=float)
    return float((net > 0).mean()) if len(net) else float("nan")


def closed_trade_metrics(trades: pd.DataFrame) -> dict:
    """Full metric dict from a trade table that has net_pnl and net_pnl_r."""
    metrics = trade_metrics(trades)
    net = trades["net_pnl"].to_numpy(float) if len(trades) else np.array([])
    r = trades["net_pnl_r"].to_numpy(float) if len(trades) else np.array([])
    metrics["expectancy_usd"] = expectancy(net)
    metrics["expectancy_r"] = expectancy(r)
    metrics["win_rate"] = win_rate(net)
    metrics["profit_factor"] = profit_factor(trades["net_pnl"] if len(trades) else pd.Series(dtype=float))
    metrics["max_drawdown_usd"] = max_drawdown(trades["net_pnl"] if len(trades) else pd.Series(dtype=float))
    metrics["max_drawdown_r"] = max_drawdown(trades["net_pnl_r"] if len(trades) else pd.Series(dtype=float))
    metrics["longest_losing_streak"] = longest_losing_streak(trades["net_pnl"] if len(trades) else pd.Series(dtype=float))
    return metrics


def by_window(trades: pd.DataFrame, window_col: str = "window") -> dict:
    out = {}
    for name, part in trades.groupby(window_col, sort=True):
        out[str(name)] = closed_trade_metrics(part)
    return out
