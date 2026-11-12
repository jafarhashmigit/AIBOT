"""Metrics, incremental value, date-block CIs."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Any

from phase50.constants import ALPHA, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, N_POLICIES_COMPARED


def summarize_run(run: dict[str, Any], *, baseline_mean: float | None = None) -> dict[str, Any]:
    decisions = run.get("decisions") or []
    rs = [float(d["realized_net_r"]) for d in decisions]
    actions = Counter(d["action"] for d in decisions)
    mean_r = sum(rs) / len(rs) if rs else None
    med = _median(rs)
    pf = _profit_factor(rs)
    dd = _max_dd(rs)
    wins = sum(1 for x in rs if x > 0)
    pairs = [(d["day"], float(d["realized_net_r"])) for d in decisions]
    boot = date_block_bootstrap(pairs)
    incr = None if baseline_mean is None or mean_r is None else mean_r - baseline_mean
    incr_pairs = [(d, v - (baseline_mean or 0)) for d, v in pairs] if baseline_mean is not None else []
    boot_incr = date_block_bootstrap(incr_pairs) if incr_pairs else {"ok": False}

    # Did learning change actions vs all-WAIT?
    changed = sum(1 for d in decisions if d["action"] != "WAIT")

    return {
        "policy_id": run.get("policy_id"),
        "experience_mode": run.get("experience_mode"),
        "n_decisions": len(decisions),
        "action_counts": dict(actions),
        "buy": actions.get("BUY", 0),
        "sell": actions.get("SELL", 0),
        "wait": actions.get("WAIT", 0),
        "wait_rate": (actions.get("WAIT", 0) / len(decisions)) if decisions else None,
        "mean_net_r": mean_r,
        "median_net_r": med,
        "win_rate": (wins / len(rs)) if rs else None,
        "profit_factor": pf,
        "max_drawdown_r": dd,
        "incremental_value_vs_baseline": incr,
        "bootstrap_mean": boot,
        "bootstrap_incremental": boot_incr,
        "n_non_wait_decisions": changed,
        "learning_changed_actions": changed > 0,
        "leakage_ok": run.get("leakage_ok"),
        "hist_n": run.get("hist_n"),
        "shadow_n": run.get("shadow_n"),
        "agent_shadow_empty": run.get("agent_shadow_empty"),
        "block_rows": run.get("block_rows"),
    }


def date_block_bootstrap(pairs: list[tuple[str, float]], n_draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    by: dict[str, list[float]] = defaultdict(list)
    for d, v in pairs:
        by[d].append(v)
    days = sorted(by)
    if len(days) < 2:
        return {"ok": False, "reason": "need>=2_dates"}
    rng = random.Random(seed)
    means = []
    for _ in range(n_draws):
        sample = [days[rng.randrange(len(days))] for _ in range(len(days))]
        vals = []
        for d in sample:
            vals.extend(by[d])
        if vals:
            means.append(sum(vals) / len(vals))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    alpha_b = ALPHA / N_POLICIES_COMPARED
    q = max(0, int(alpha_b * len(means)))
    qh = min(len(means) - 1, int((1 - alpha_b) * len(means)) - 1)
    return {
        "ok": True,
        "n_dates": len(days),
        "mean": sum(means) / len(means),
        "ci95_low": lo,
        "ci95_high": hi,
        "bonferroni_ci_low": means[q],
        "bonferroni_ci_high": means[qh],
        "bonferroni_excludes_zero": means[q] > 0 or means[qh] < 0,
        "ci95_excludes_zero": lo > 0 or hi < 0,
    }


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    return ys[mid] if n % 2 else 0.5 * (ys[mid - 1] + ys[mid])


def _profit_factor(xs: list[float]) -> float | None:
    gains = sum(x for x in xs if x > 0)
    losses = sum(-x for x in xs if x < 0)
    if losses <= 0:
        return None if gains <= 0 else float("inf")
    return gains / losses


def _max_dd(xs: list[float]) -> float | None:
    if not xs:
        return None
    peak = eq = 0.0
    mdd = 0.0
    for x in xs:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return mdd


def comparison_table(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for s in summaries:
        boot = s.get("bootstrap_incremental") or {}
        rows.append(
            {
                "Policy": s.get("policy_id"),
                "Experience Source": s.get("experience_mode"),
                "Decisions": s.get("n_decisions"),
                "BUY": s.get("buy"),
                "SELL": s.get("sell"),
                "WAIT": s.get("wait"),
                "Mean Net R": s.get("mean_net_r"),
                "Median R": s.get("median_net_r"),
                "PF": s.get("profit_factor"),
                "DD": s.get("max_drawdown_r"),
                "Incremental Value": s.get("incremental_value_vs_baseline"),
                "CI95 incr": (
                    [boot.get("ci95_low"), boot.get("ci95_high")] if boot.get("ok") else None
                ),
            }
        )
    return rows
