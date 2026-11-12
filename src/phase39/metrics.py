"""Performance metrics — date-aware, no pooling illusion."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any


def summarize(trades: list[dict[str, Any]]) -> dict[str, Any]:
    # Score PASS/FAIL/TIMEOUT and adverse EXECUTION_UNCERTAIN; exclude coverage gaps
    scored = [
        t
        for t in trades
        if t.get("net_r") is not None and t.get("status") != "INSUFFICIENT_TICK_COVERAGE"
    ]
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
    # drawdown on chronological scored
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    consec = 0
    max_consec = 0
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
    }


def by_date(trades: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        if t.get("net_r") is None or t.get("status") == "INSUFFICIENT_TICK_COVERAGE":
            continue
        groups[t.get("day") or "unknown"].append(t)
    out = {}
    for day, ts in sorted(groups.items()):
        rs = [float(x["net_r"]) for x in ts]
        out[day] = {"n": len(ts), "mean_r": sum(rs) / len(rs), "sum_r": sum(rs)}
    return out


def day_block_bootstrap(trades: list[dict[str, Any]], n_draws: int = 1000, seed: int = 39) -> dict[str, Any]:
    scored = [t for t in trades if t.get("net_r") is not None and t.get("status") != "INSUFFICIENT_TICK_COVERAGE"]
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
        vals = []
        for d in sample_days:
            vals.extend(by_d[d])
        if vals:
            means.append(sum(vals) / len(vals))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    return {
        "ok": True,
        "n_dates": len(days),
        "n_draws": n_draws,
        "ci95_low": lo,
        "ci95_high": hi,
        "ci95_excludes_zero": lo > 0 or hi < 0,
        "prob_mean_r_le_0": sum(1 for m in means if m <= 0) / len(means),
        "dependent_on_one_date": max(len(v) for v in by_d.values()) / max(1, len(scored)) > 0.6,
    }


def break_even_cost(trades: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [t for t in trades if t.get("net_r") is not None and t.get("initial_risk")]
    if not scored:
        return {"ok": False}
    # max uniform extra USD per trade before mean net_r = 0
    # net_r' = (net_pnl - c) / risk ; mean((pnl-c)/risk)=0 => c = mean(pnl) / mean? better: solve mean((pnl-c)/risk)=0
    # sum((pnl_i - c)/risk_i)=0 => c = sum(pnl/risk)*? Actually sum(pnl_i/risk_i) = c * sum(1/risk_i)
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
