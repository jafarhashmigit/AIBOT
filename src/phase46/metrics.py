"""Diagnostic metrics for costed EV baselines (not edge claims)."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any

from phase46.constants import ALPHA, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED


def _finite(xs: list[float | None]) -> list[float]:
    out: list[float] = []
    for x in xs:
        if x is None:
            continue
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            continue
        out.append(float(x))
    return out


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def median(xs: list[float]) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return ys[mid]
    return 0.5 * (ys[mid - 1] + ys[mid])


def profit_factor(xs: list[float]) -> float | None:
    gains = sum(x for x in xs if x > 0)
    losses = sum(-x for x in xs if x < 0)
    if losses <= 0:
        return None if gains <= 0 else float("inf")
    return gains / losses


def max_drawdown(xs: list[float]) -> float | None:
    if not xs:
        return None
    peak = 0.0
    equity = 0.0
    mdd = 0.0
    for x in xs:
        equity += x
        peak = max(peak, equity)
        mdd = min(mdd, equity - peak)
    return mdd


def date_block_bootstrap_ci(
    pairs: list[tuple[str, float]],
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    by_day: dict[str, list[float]] = defaultdict(list)
    for d, v in pairs:
        by_day[d].append(v)
    days = sorted(by_day.keys())
    if len(days) < 2:
        return {"ok": False, "reason": "need>=2_dates"}
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_draws):
        sample = [days[rng.randrange(len(days))] for _ in range(len(days))]
        vals: list[float] = []
        for d in sample:
            vals.extend(by_day[d])
        if vals:
            means.append(sum(vals) / len(vals))
    if not means:
        return {"ok": False}
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    return {
        "ok": True,
        "n_dates": len(days),
        "ci95_low": lo,
        "ci95_high": hi,
        "mean_boot": sum(means) / len(means),
        "alpha": ALPHA,
        "prob_mean_le_0": sum(1 for m in means if m <= 0) / len(means),
    }


def summarize_net_r(
    outcomes: list[dict[str, Any]],
    *,
    scenario_id: str = "OBSERVED_BIDASK_ONLY",
) -> dict[str, Any]:
    pairs: list[tuple[str, float]] = []
    gross_vals: list[float] = []
    net_vals: list[float] = []
    for o in outcomes:
        if o.get("data_quality_status") != "OK" and o.get("action") != "WAIT":
            # WAIT with INVALID_RISK still has defined 0 when risk ok; skip bad directional
            if o.get("action") != "WAIT":
                continue
        if o.get("action") == "WAIT":
            nr = o.get("net_r")
            gr = o.get("gross_r")
        else:
            sn = (o.get("scenario_nets") or {}).get(scenario_id) or {}
            nr = sn.get("net_r", o.get("net_r"))
            gr = o.get("gross_r")
        if nr is None:
            continue
        day = str(o.get("day") or "")
        pairs.append((day, float(nr)))
        net_vals.append(float(nr))
        if gr is not None:
            gross_vals.append(float(gr))

    wins = sum(1 for x in net_vals if x > 0)
    return {
        "scenario_id": scenario_id,
        "n": len(net_vals),
        "mean_gross_r": mean(gross_vals),
        "mean_net_r": mean(net_vals),
        "median_net_r": median(net_vals),
        "win_rate": (wins / len(net_vals)) if net_vals else None,
        "profit_factor": profit_factor(net_vals),
        "max_drawdown_net_r_path": max_drawdown(net_vals),
        "bootstrap": date_block_bootstrap_ci(pairs),
    }
