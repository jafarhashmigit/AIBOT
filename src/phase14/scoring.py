"""Economic and statistical scoring for Phase 14 trades."""

from __future__ import annotations

import math

import numpy as np

from phase3.nplib import day_cluster_bootstrap_mean, max_drawdown, profit_factor, win_rate
from phase14.constants import BOOTSTRAP_DRAWS, FOLDS, SEED, SPREAD_FLOOR_USD


def stress_net_r(net_r: float, initial_risk: float, mult: float, extra_slippage_usd: float = 0.0) -> float:
    if initial_risk <= 0:
        return float("nan")
    extra = (mult - 1.0) * SPREAD_FLOOR_USD + extra_slippage_usd
    return net_r - extra / initial_risk


def _block(rows: list[dict], *, r_key: str = "net_r") -> dict:
    if not rows:
        return {
            "n": 0,
            "mean_r": float("nan"),
            "median_r": float("nan"),
            "net_r": 0.0,
            "net_usd": 0.0,
            "profit_factor": float("nan"),
            "win_rate": float("nan"),
            "max_drawdown_usd": 0.0,
            "bootstrap": {
                "mean": float("nan"),
                "ci_low": float("nan"),
                "ci_high": float("nan"),
                "p_mean_le_0": float("nan"),
                "n_days": 0,
                "n_samples": BOOTSTRAP_DRAWS,
                "seed": SEED,
            },
            "n_days": 0,
        }
    r = np.asarray([x[r_key] for x in rows], dtype=float)
    pnl = np.asarray([x["net_pnl"] for x in rows], dtype=float)
    times = [x["decision_time"] for x in rows]
    boot = day_cluster_bootstrap_mean(times, r, n_samples=BOOTSTRAP_DRAWS, seed=SEED)
    days = {t[:10] for t in times}
    return {
        "n": int(len(rows)),
        "mean_r": float(r.mean()),
        "median_r": float(np.median(r)),
        "net_r": float(r.sum()),
        "net_usd": float(pnl.sum()),
        "profit_factor": float(profit_factor(r)),
        "win_rate": float(win_rate(r)),
        "max_drawdown_usd": float(max_drawdown(pnl)),
        "bootstrap": boot,
        "n_days": len(days),
    }


def score_trades(trades: list[dict], *, label: str = "primary") -> dict:
    by_fold = {fid: [] for fid in FOLDS}
    by_side = {"BUY": [], "SELL": []}
    for row in trades:
        by_fold[row["fold_id"]].append(row)
        by_side[row["side"]].append(row)

    pooled = _block(trades)
    folds = {fid: _block(rows) for fid, rows in by_fold.items()}
    sides = {side: _block(rows) for side, rows in by_side.items()}

    # Consecutive loss streaks
    streak = 0
    max_streak = 0
    for row in sorted(trades, key=lambda x: x["decision_time"]):
        if row["net_r"] < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return {
        "label": label,
        "pooled": pooled,
        "folds": folds,
        "sides": sides,
        "max_consecutive_losses": max_streak,
        "all_folds_positive": all(
            folds[fid]["n"] == 0 or (folds[fid]["mean_r"] == folds[fid]["mean_r"] and folds[fid]["mean_r"] > 0)
            for fid in FOLDS
        ),
        "all_active_folds_positive": all(
            folds[fid]["mean_r"] > 0
            for fid in FOLDS
            if folds[fid]["n"] >= 1 and folds[fid]["mean_r"] == folds[fid]["mean_r"]
        ),
    }


def cost_robustness(trades: list[dict], multipliers: tuple[float, ...], extra_slippage_usd: float = 0.0) -> dict:
    out = {}
    for mult in multipliers:
        stressed = []
        for row in trades:
            rr = dict(row)
            rr["net_r"] = stress_net_r(row["net_r"], row["initial_risk"], mult, extra_slippage_usd)
            # approximate USD stress proportional to R stress delta
            delta_r = rr["net_r"] - row["net_r"]
            rr["net_pnl"] = row["net_pnl"] + delta_r * row["initial_risk"]
            stressed.append(rr)
        block = _block(stressed)
        out[f"{mult:g}x"] = {
            "multiplier": mult,
            "extra_slippage_usd": extra_slippage_usd,
            "n": block["n"],
            "mean_r": block["mean_r"],
            "net_usd": block["net_usd"],
            "bootstrap": block["bootstrap"],
            "mean_r_positive": block["mean_r"] == block["mean_r"] and block["mean_r"] > 0,
        }
    return out


def session_vol_breakdown(trades: list[dict]) -> dict:
    ny = [t for t in trades if t.get("session_ny") == 1]
    non_ny = [t for t in trades if t.get("session_ny") == 0]
    atrs = [t["atr_14_pct"] for t in trades if t.get("atr_14_pct") is not None]
    if atrs:
        xs = sorted(atrs)
        p33 = xs[int(0.33 * (len(xs) - 1))]
        p67 = xs[int(0.67 * (len(xs) - 1))]
    else:
        p33 = p67 = float("nan")

    def atr_bucket(v):
        if v != v:
            return "unknown"
        if v <= p33:
            return "low"
        if v <= p67:
            return "mid"
        return "high"

    buckets = {"low": [], "mid": [], "high": [], "unknown": []}
    for t in trades:
        buckets[atr_bucket(t.get("atr_14_pct"))].append(t)

    return {
        "session_ny": _block(ny),
        "session_non_ny": _block(non_ny),
        "atr_tercile": {k: _block(v) for k, v in buckets.items()},
        "atr_cuts_from_trade_set_diagnostic_only": {"p33": p33, "p67": p67},
    }


def wf1_negative_investigation(trades: list[dict], score: dict) -> dict:
    wf1 = [t for t in trades if t["fold_id"] == "WF1"]
    wf2 = [t for t in trades if t["fold_id"] == "WF2"]
    wf3 = [t for t in trades if t["fold_id"] == "WF3"]
    return {
        "wf1_mean_r": score["folds"]["WF1"]["mean_r"],
        "wf2_mean_r": score["folds"]["WF2"]["mean_r"],
        "wf3_mean_r": score["folds"]["WF3"]["mean_r"],
        "wf1_n": len(wf1),
        "wf1_buy_n": sum(1 for t in wf1 if t["side"] == "BUY"),
        "wf1_sell_n": sum(1 for t in wf1 if t["side"] == "SELL"),
        "wf1_buy_mean_r": float(np.mean([t["net_r"] for t in wf1 if t["side"] == "BUY"])) if any(t["side"] == "BUY" for t in wf1) else float("nan"),
        "wf1_sell_mean_r": float(np.mean([t["net_r"] for t in wf1 if t["side"] == "SELL"])) if any(t["side"] == "SELL" for t in wf1) else float("nan"),
        "wf1_ny_share": (sum(1 for t in wf1 if t.get("session_ny") == 1) / len(wf1)) if wf1 else float("nan"),
        "wf2_ny_share": (sum(1 for t in wf2 if t.get("session_ny") == 1) / len(wf2)) if wf2 else float("nan"),
        "wf3_ny_share": (sum(1 for t in wf3 if t.get("session_ny") == 1) / len(wf3)) if wf3 else float("nan"),
        "interpretation": (
            "WF1 underperformance is investigated descriptively only. "
            "No parameter is changed to improve WF1."
        ),
    }
