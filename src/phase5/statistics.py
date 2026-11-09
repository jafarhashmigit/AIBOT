"""Day-cluster bootstrap and concentration diagnostics."""

from __future__ import annotations

import numpy as np

from phase3.nplib import day_cluster_bootstrap_mean, max_drawdown, profit_factor, win_rate
from phase5.constants import N_BOOT, SEED, SPREAD_FLOOR_USD, SPREAD_STRESS


def trade_metrics(r: np.ndarray, pnl: np.ndarray) -> dict:
    n = int(len(r))
    if n == 0:
        return {
            "n": 0, "mean_r": float("nan"), "median_r": float("nan"), "total_r": 0.0,
            "net_pnl": 0.0, "profit_factor": float("nan"), "win_rate": float("nan"),
            "max_drawdown_usd": 0.0, "max_drawdown_r": 0.0, "average_trade_usd": float("nan"),
            "largest_win_r": float("nan"), "largest_loss_r": float("nan"),
        }
    return {
        "n": n,
        "mean_r": float(r.mean()),
        "median_r": float(np.median(r)),
        "total_r": float(r.sum()),
        "net_pnl": float(pnl.sum()),
        "profit_factor": profit_factor(pnl),
        "win_rate": win_rate(pnl),
        "max_drawdown_usd": max_drawdown(pnl),
        "max_drawdown_r": max_drawdown(r),
        "average_trade_usd": float(pnl.mean()),
        "largest_win_r": float(r.max()),
        "largest_loss_r": float(r.min()),
    }


def bootstrap_mean_r(times: list, r: np.ndarray) -> dict:
    return day_cluster_bootstrap_mean(times, r, n_samples=N_BOOT, seed=SEED)


def cost_stress(pnl: np.ndarray, r: np.ndarray) -> dict:
    out = {}
    risk = np.full(len(r), np.nan)
    ok = np.isfinite(pnl) & np.isfinite(r) & (np.abs(r) > 1e-12)
    risk[ok] = pnl[ok] / r[ok]
    usable = ok & np.isfinite(risk) & (risk > 0)
    for mult in SPREAD_STRESS:
        extra = (mult - 1.0) * SPREAD_FLOOR_USD
        sr = np.array(r, dtype=float)
        sp = np.array(pnl, dtype=float)
        sp[usable] = pnl[usable] - extra
        sr[usable] = sp[usable] / risk[usable]
        out[f"spread_x{mult}"] = {
            "multiplier": mult,
            "extra_usd": extra,
            "n": int(usable.sum()),
            "mean_r": float(sr[usable].mean()) if usable.any() else float("nan"),
            "net_pnl": float(sp[usable].sum()) if usable.any() else 0.0,
            "profit_factor": profit_factor(sp[usable]) if usable.any() else float("nan"),
        }
    return out


def concentration(times: list[str], r: np.ndarray, pnl: np.ndarray) -> dict:
    n = len(r)
    if n == 0:
        return {"n": 0}
    order = np.argsort(r)
    losers = order[: min(5, n)]
    winners = order[-min(5, n):][::-1]
    total = float(r.sum())
    best = float(r[order[-1]])
    worst = float(r[order[0]])
    top1 = max(1, int(np.ceil(0.01 * n)))
    top1_share = float(r[order[-top1:]].sum() / total) if total != 0 else float("nan")
    streak = longest = 0
    for val in r:
        if val <= 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0

    def pack(idx):
        return [{"decision_time": times[i], "net_r": float(r[i]), "net_pnl": float(pnl[i])} for i in idx]

    return {
        "best_trade_r": best,
        "worst_trade_r": worst,
        "best_share_of_total_r": (best / total) if total else float("nan"),
        "worst_share_of_total_r": (worst / total) if total else float("nan"),
        "top_5_winners": pack(winners),
        "top_5_losers": pack(losers),
        "top_1pct_n": top1,
        "top_1pct_share_of_total_r": top1_share,
        "longest_losing_streak": int(longest),
        "note": "Shares can exceed 1 in absolute value when total R is small.",
    }
