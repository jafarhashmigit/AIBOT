"""Outer-OOS evaluation, comparison, bootstrap, and stress tests."""

from __future__ import annotations

import numpy as np

from phase3.constants import PERTURBATIONS, SEED, SPREAD_FLOOR_USD, SPREAD_STRESS_MULTIPLIERS
from phase3.decision_policy import decide_batch, realized_from_action
from phase3.nplib import col, day_cluster_bootstrap_mean, max_drawdown, profit_factor, win_rate


def economic_from_actions(rows: list[dict], actions: np.ndarray) -> dict:
    n_decisions = int(len(actions))
    n_buy = int((actions == "BUY").sum())
    n_sell = int((actions == "SELL").sum())
    n_wait = int((actions == "WAIT").sum())
    r_all, pnl_all, reason = realized_from_action(rows, actions)
    executed = actions != "WAIT"
    n_trades = int(executed.sum())
    trade_rate = n_trades / n_decisions if n_decisions else float("nan")
    decision_r = np.where(executed, r_all, 0.0)
    out = {
        "n_decisions": n_decisions,
        "n_buy": n_buy,
        "n_sell": n_sell,
        "n_wait": n_wait,
        "n_trades": n_trades,
        "trade_rate": float(trade_rate),
        "mean_r_per_decision": float(decision_r.mean()) if n_decisions else float("nan"),
        "mean_r_per_trade": float(r_all[executed].mean()) if n_trades else float("nan"),
        "median_r_per_trade": float(np.median(r_all[executed])) if n_trades else float("nan"),
        "net_r": float(r_all[executed].sum()) if n_trades else 0.0,
        "net_pnl": float(pnl_all[executed].sum()) if n_trades else 0.0,
        "profit_factor": profit_factor(pnl_all[executed]) if n_trades else float("nan"),
        "win_rate": win_rate(pnl_all[executed]) if n_trades else float("nan"),
        "max_drawdown_usd": max_drawdown(pnl_all[executed]) if n_trades else 0.0,
        "max_drawdown_r": max_drawdown(r_all[executed]) if n_trades else 0.0,
        "worst_trade_r": float(r_all[executed].min()) if n_trades else float("nan"),
        "best_trade_r": float(r_all[executed].max()) if n_trades else float("nan"),
        "expectancy_usd": float(pnl_all[executed].mean()) if n_trades else float("nan"),
        "costs_note": "P&L already includes approved spread floor and $0.05/side from Phase 1 side outcomes.",
    }
    for side in ("BUY", "SELL"):
        mask = actions == side
        out[f"{side.lower()}_n"] = int(mask.sum())
        out[f"{side.lower()}_mean_r"] = float(r_all[mask].mean()) if mask.any() else float("nan")
        out[f"{side.lower()}_net_pnl"] = float(pnl_all[mask].sum()) if mask.any() else 0.0
        out[f"{side.lower()}_pf"] = profit_factor(pnl_all[mask]) if mask.any() else float("nan")
    times = [r["decision_time"] for r in rows]
    if n_trades:
        trade_times = [t for t, e in zip(times, executed) if e]
        out["day_cluster_bootstrap_mean_trade_r"] = day_cluster_bootstrap_mean(
            trade_times, r_all[executed], n_samples=2000, seed=SEED)
    else:
        out["day_cluster_bootstrap_mean_trade_r"] = {
            "mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
            "p_mean_le_0": float("nan"), "n_samples": 2000, "seed": SEED,
            "method": "day_cluster", "n_days": 0, "note": "no trades",
        }
    out["day_cluster_bootstrap_mean_decision_r"] = day_cluster_bootstrap_mean(
        times, decision_r, n_samples=2000, seed=SEED)
    out["sample_too_small"] = bool(n_trades < 50)
    return out


def by_fold(rows: list[dict], actions: np.ndarray, fold_key: str = "fold_id") -> dict:
    out = {}
    folds = [r[fold_key] for r in rows]
    for fold in dict.fromkeys(folds):
        mask = np.array([f == fold for f in folds])
        part = [row for row, keep in zip(rows, mask) if keep]
        out[str(fold)] = economic_from_actions(part, actions[mask])
    return out


def compare_policies(rows: list[dict], policy_actions: dict[str, np.ndarray]) -> dict:
    reports = {}
    for name, actions in policy_actions.items():
        reports[name] = {
            "pooled": economic_from_actions(rows, actions),
            "by_outer_fold": by_fold(rows, actions),
        }
    return reports


def stress_spread(rows: list[dict], actions: np.ndarray) -> dict:
    r, pnl, _ = realized_from_action(rows, actions)
    executed = actions != "WAIT"
    risk = np.full(len(pnl), np.nan)
    ok = np.isfinite(pnl) & np.isfinite(r) & (np.abs(r) > 1e-12)
    risk[ok] = pnl[ok] / r[ok]
    out = {}
    for mult in SPREAD_STRESS_MULTIPLIERS:
        extra = (mult - 1.0) * SPREAD_FLOOR_USD
        stressed_pnl = pnl.copy()
        stressed_r = r.copy()
        usable = executed & np.isfinite(risk) & (risk > 0)
        stressed_pnl[usable] = pnl[usable] - extra
        stressed_r[usable] = stressed_pnl[usable] / risk[usable]
        n = int(usable.sum())
        out[f"spread_x{mult}"] = {
            "multiplier": mult,
            "extra_usd_per_trade": extra,
            "n_trades_with_risk": n,
            "n_trades_missing_risk": int(executed.sum() - n),
            "mean_trade_r": float(stressed_r[usable].mean()) if n else float("nan"),
            "net_pnl": float(stressed_pnl[usable].sum()) if n else 0.0,
            "profit_factor": profit_factor(stressed_pnl[usable]) if n else float("nan"),
        }
    return out


def stress_threshold(rows: list[dict], ev_buy: np.ndarray, ev_sell: np.ndarray,
                     tau, min_gap: float) -> dict:
    if tau is None:
        return {"note": "frozen policy is Always-WAIT on this fold; perturbation not applicable"}
    out = {}
    for delta in PERTURBATIONS:
        new_tau = float(tau) + delta
        actions = decide_batch(ev_buy, ev_sell, new_tau, min_gap)
        out[f"tau_{new_tau:.4f}"] = economic_from_actions(rows, actions)
    return out


def phase3_economic_gate(pooled: dict, by_outer: dict, stress: dict, leak_passed: bool) -> dict:
    mean_r = pooled.get("mean_r_per_trade")
    fold_means = {k: v.get("mean_r_per_trade") for k, v in by_outer.items()}
    finite_means = [v for v in fold_means.values() if v is not None and np.isfinite(v)]
    n_pos = sum(v > 0 for v in finite_means)
    majority_pos = n_pos > (len(finite_means) / 2) if finite_means else False
    boot = pooled.get("day_cluster_bootstrap_mean_trade_r") or {}
    ci_low = boot.get("ci_low")
    n_trades = pooled.get("n_trades") or 0
    buy_n = pooled.get("n_buy") or 0
    sell_n = pooled.get("n_sell") or 0
    one_side = (n_trades > 0) and (buy_n == 0 or sell_n == 0)
    cost_ok = True
    for rec in (stress.get("spread") or {}).values():
        if isinstance(rec, dict) and rec.get("mean_trade_r") is not None:
            if np.isfinite(rec["mean_trade_r"]) and rec["mean_trade_r"] <= 0:
                cost_ok = False
    pert_ok = True
    for rec in (stress.get("threshold") or {}).values():
        if isinstance(rec, dict) and rec.get("mean_r_per_trade") is not None:
            if np.isfinite(rec["mean_r_per_trade"]) and rec["mean_r_per_trade"] <= 0:
                pert_ok = False
    criteria = {
        "mean_trade_r_positive": bool(mean_r is not None and np.isfinite(mean_r) and mean_r > 0),
        "majority_outer_folds_positive": bool(majority_pos),
        "ci_low_above_zero": bool(ci_low is not None and np.isfinite(ci_low) and ci_low > 0),
        "not_tiny_trade_count": bool(n_trades >= 50),
        "not_single_side_artifact": bool(n_trades == 0 or not one_side),
        "cost_stress_still_positive": bool(cost_ok) if n_trades else False,
        "threshold_perturbation_still_positive": bool(pert_ok) if n_trades else False,
        "leakage_audit_passed": bool(leak_passed),
    }
    return {
        "passed": all(criteria.values()),
        "criteria": criteria,
        "fold_mean_trade_r": fold_means,
        "n_positive_folds": n_pos,
        "n_folds": len(finite_means),
        "conclusion_if_failed": "NO CREDIBLE ECONOMIC EDGE",
        "note": "A pass is required to consider a potentially credible edge. "
                "Phase 1 permutation A remains not_run and is not this gate.",
    }
