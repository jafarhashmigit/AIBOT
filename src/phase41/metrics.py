"""Performance metrics — date-aware, multiple-testing aware."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any

from phase41.constants import BONFERRONI_ALPHA


def _scored(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        t
        for t in trades
        if t.get("net_r") is not None and t.get("status") != "INSUFFICIENT_TICK_COVERAGE"
    ]


def summarize(trades: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _scored(trades)
    if not scored:
        return {
            "n_signals": len(trades),
            "n_scored": 0,
            "n_insufficient_coverage": sum(1 for t in trades if t.get("status") == "INSUFFICIENT_TICK_COVERAGE"),
            "n_uncertain": sum(1 for t in trades if t.get("uncertain")),
            "mean_r": None,
            "median_r": None,
            "win_rate": None,
            "profit_factor": None,
            "max_dd_r": None,
            "max_consec_losses": None,
        }
    rs = [float(t["net_r"]) for t in scored]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gp = sum(wins)
    gl = abs(sum(losses))
    eq = peak = max_dd = 0.0
    consec = max_consec = 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
        if r <= 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    s = sorted(rs)
    mid = s[len(s) // 2] if len(s) % 2 == 1 else 0.5 * (s[len(s) // 2 - 1] + s[len(s) // 2])
    buys = [t for t in scored if t.get("side") == "BUY"]
    sells = [t for t in scored if t.get("side") == "SELL"]
    holds = [t.get("hold_ms") for t in scored if t.get("hold_ms") is not None]
    spreads = [float(t.get("entry_spread") or 0) for t in scored]
    return {
        "n_signals": len(trades),
        "n_scored": len(scored),
        "n_insufficient_coverage": sum(1 for t in trades if t.get("status") == "INSUFFICIENT_TICK_COVERAGE"),
        "n_uncertain": sum(1 for t in trades if t.get("uncertain")),
        "n_buy": len(buys),
        "n_sell": len(sells),
        "mean_r": sum(rs) / len(rs),
        "median_r": mid,
        "win_rate": len(wins) / len(rs),
        "profit_factor": (gp / gl) if gl > 0 else (None if gp == 0 else float("inf")),
        "max_dd_r": max_dd,
        "max_consec_losses": max_consec,
        "mean_mae_r": sum(float(t.get("mae_r") or 0) for t in scored) / len(scored),
        "mean_mfe_r": sum(float(t.get("mfe_r") or 0) for t in scored) / len(scored),
        "buy_mean_r": (sum(float(t["net_r"]) for t in buys) / len(buys)) if buys else None,
        "sell_mean_r": (sum(float(t["net_r"]) for t in sells) / len(sells)) if sells else None,
        "mean_entry_spread": (sum(spreads) / len(spreads)) if spreads else None,
        "median_hold_ms": (sorted(holds)[len(holds) // 2] if holds else None),
        "exit_reason_counts": {
            k: sum(1 for t in scored if t.get("exit_reason") == k) for k in ("PASS", "FAIL", "TIMEOUT")
        },
    }


def by_date_all(trades: list[dict[str, Any]], all_dates: list[str]) -> dict[str, Any]:
    """Include dates with zero scored trades."""
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        if t.get("net_r") is None or t.get("status") == "INSUFFICIENT_TICK_COVERAGE":
            continue
        groups[t.get("day") or "unknown"].append(t)
    out = {}
    for day in all_dates:
        ts = groups.get(day) or []
        if not ts:
            out[day] = {"n": 0, "mean_r": None, "sum_r": 0.0, "n_signals": sum(1 for t in trades if t.get("day") == day)}
            continue
        rs = [float(x["net_r"]) for x in ts]
        out[day] = {
            "n": len(ts),
            "mean_r": sum(rs) / len(rs),
            "sum_r": sum(rs),
            "n_signals": sum(1 for t in trades if t.get("day") == day),
        }
    return out


def by_session(trades: list[dict[str, Any]]) -> dict[str, Any]:
    buckets = {"asia": [], "london": [], "new_york": [], "other": []}
    for t in _scored(trades):
        hour = int(str(t.get("signal_time") or "00")[11:13])
        if 0 <= hour < 7:
            buckets["asia"].append(float(t["net_r"]))
        elif 7 <= hour < 12:
            buckets["london"].append(float(t["net_r"]))
        elif 12 <= hour < 21:
            buckets["new_york"].append(float(t["net_r"]))
        else:
            buckets["other"].append(float(t["net_r"]))
    out = {}
    for k, vals in buckets.items():
        out[k] = {
            "n": len(vals),
            "mean_r": (sum(vals) / len(vals)) if vals else None,
        }
    return out


def day_block_bootstrap(trades: list[dict[str, Any]], n_draws: int = 2000, seed: int = 41) -> dict[str, Any]:
    scored = _scored(trades)
    by_d: dict[str, list[float]] = defaultdict(list)
    for t in scored:
        by_d[t.get("day") or "?"].append(float(t["net_r"]))
    days = list(by_d.keys())
    if len(days) < 2 or not scored:
        return {"ok": False, "reason": "need>=2_dates_with_scored_trades", "n_dates": len(days)}
    rng = random.Random(seed)
    means = []
    for _ in range(n_draws):
        sample_days = [days[rng.randrange(len(days))] for _ in range(len(days))]
        vals: list[float] = []
        for d in sample_days:
            vals.extend(by_d[d])
        if vals:
            means.append(sum(vals) / len(vals))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    p_le0 = sum(1 for m in means if m <= 0) / len(means)
    # Bonferroni for 2 candidates: effective one-sided alpha = BONFERRONI_ALPHA/2
    alpha_adj = BONFERRONI_ALPHA / 2.0
    # Approximate: CI that excludes 0 at family-wise level requires stricter quantile
    q_lo = int(alpha_adj * len(means))
    q_hi = int((1.0 - alpha_adj) * len(means)) - 1
    q_lo = max(0, min(q_lo, len(means) - 1))
    q_hi = max(0, min(q_hi, len(means) - 1))
    return {
        "ok": True,
        "n_dates": len(days),
        "n_draws": n_draws,
        "ci95_low": lo,
        "ci95_high": hi,
        "ci95_excludes_zero": lo > 0 or hi < 0,
        "prob_mean_r_le_0": p_le0,
        "bonferroni_alpha_per_candidate": alpha_adj,
        "bonferroni_ci_low": means[q_lo],
        "bonferroni_ci_high": means[q_hi],
        "bonferroni_ci_excludes_zero": means[q_lo] > 0 or means[q_hi] < 0,
        "dependent_on_one_date": max(len(v) for v in by_d.values()) / max(1, len(scored)) > 0.6,
        "note": "Exploratory retest on previously examined dates — not independent OOS confirmation",
    }


def leave_one_date_out(trades: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _scored(trades)
    by_d: dict[str, list[float]] = defaultdict(list)
    for t in scored:
        by_d[t.get("day") or "?"].append(float(t["net_r"]))
    days = sorted(by_d.keys())
    if len(days) < 2:
        return {"ok": False, "reason": "need>=2_dates"}
    rows = []
    for held in days:
        vals = []
        for d, rs in by_d.items():
            if d == held:
                continue
            vals.extend(rs)
        mean_r = sum(vals) / len(vals) if vals else None
        rows.append({"held_out_date": held, "n_remaining": len(vals), "mean_r": mean_r})
    signs = [1 if (r["mean_r"] or 0) > 0 else (-1 if (r["mean_r"] or 0) < 0 else 0) for r in rows]
    return {
        "ok": True,
        "rows": rows,
        "all_folds_positive": all(s > 0 for s in signs),
        "all_folds_negative": all(s < 0 for s in signs),
        "sign_flip_count": sum(1 for i in range(1, len(signs)) if signs[i] != signs[0]),
    }


def break_even_cost(trades: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [t for t in _scored(trades) if t.get("initial_risk")]
    if not scored:
        return {"ok": False}
    s_r = sum(float(t["net_pnl"]) / float(t["initial_risk"]) for t in scored)
    s_inv = sum(1.0 / float(t["initial_risk"]) for t in scored)
    c_star = (s_r / s_inv) if s_inv else None
    return {
        "ok": True,
        "max_extra_usd_per_trade_before_zero_expectancy": c_star,
        "note": "Uniform extra cost c such that mean(net_r)=0 under observed bid/ask fills",
        "n": len(scored),
        "observed_mean_r": s_r / len(scored),
    }
