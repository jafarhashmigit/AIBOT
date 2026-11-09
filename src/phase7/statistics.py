"""Approved day-cluster bootstrap and trade metrics. Not a new test."""

from __future__ import annotations

import numpy as np

from phase3.nplib import day_cluster_bootstrap_mean, max_drawdown, profit_factor, win_rate
from phase7.constants import N_BOOT, SEED


def longest_losing_streak(r: np.ndarray) -> int:
    streak = longest = 0
    for val in r:
        if val <= 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    return int(longest)


def trade_metrics(r: np.ndarray, pnl: np.ndarray) -> dict:
    r = np.asarray(r, dtype=float)
    pnl = np.asarray(pnl, dtype=float)
    n = int(len(r))
    if n == 0:
        return {
            "trade_count": 0,
            "mean_r": float("nan"),
            "median_r": float("nan"),
            "total_r": 0.0,
            "net_pnl": 0.0,
            "profit_factor": float("nan"),
            "win_rate": float("nan"),
            "max_drawdown_usd": 0.0,
            "max_drawdown_r": 0.0,
            "average_trade": float("nan"),
            "largest_win": float("nan"),
            "largest_loss": float("nan"),
            "losing_streak": 0,
        }
    return {
        "trade_count": n,
        "mean_r": float(r.mean()),
        "median_r": float(np.median(r)),
        "total_r": float(r.sum()),
        "net_pnl": float(pnl.sum()),
        "profit_factor": profit_factor(pnl),
        "win_rate": win_rate(pnl),
        "max_drawdown_usd": max_drawdown(pnl),
        "max_drawdown_r": max_drawdown(r),
        "average_trade": float(pnl.mean()),
        "largest_win": float(r.max()),
        "largest_loss": float(r.min()),
        "losing_streak": longest_losing_streak(r),
    }


def bootstrap_trade_r(times: list, r: np.ndarray) -> dict:
    if len(r) < 2:
        return {
            "mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
            "p_mean_le_0": float("nan"), "n_samples": N_BOOT, "seed": SEED,
            "method": "day_cluster", "n_days": 0, "note": "insufficient trades",
        }
    return day_cluster_bootstrap_mean(times, r, n_samples=N_BOOT, seed=SEED)
