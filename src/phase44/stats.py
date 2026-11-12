"""Date-block bootstrap and LODO."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from phase44.constants import ALPHA, BONFERRONI_N


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def group_by_day(pairs: list[tuple[str, float]]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for d, v in pairs:
        out[d].append(v)
    return dict(out)


def date_block_bootstrap_vs_zero(cond_by_day: dict[str, list[float]], n_draws: int = 1500, seed: int = 44) -> dict[str, Any]:
    days = sorted(cond_by_day.keys())
    if len(days) < 2:
        return {"ok": False, "reason": "need>=2_dates"}
    rng = random.Random(seed)
    means = []
    for _ in range(n_draws):
        sample = [days[rng.randrange(len(days))] for _ in range(len(days))]
        vals = []
        for d in sample:
            vals.extend(cond_by_day[d])
        if vals:
            means.append(sum(vals) / len(vals))
    if not means:
        return {"ok": False}
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    alpha_b = ALPHA / BONFERRONI_N
    q = max(0, int(alpha_b * len(means)))
    qh = min(len(means) - 1, int((1 - alpha_b) * len(means)) - 1)
    return {
        "ok": True,
        "n_dates": len(days),
        "ci95_low": lo,
        "ci95_high": hi,
        "ci95_excludes_zero": lo > 0 or hi < 0,
        "prob_mean_le_0": sum(1 for m in means if m <= 0) / len(means),
        "bonferroni_alpha": alpha_b,
        "bonferroni_ci_low": means[q],
        "bonferroni_ci_high": means[qh],
        "bonferroni_excludes_zero": means[q] > 0 or means[qh] < 0,
        "mean_effect": sum(means) / len(means),
    }


def leave_one_date_out(cond_by_day: dict[str, list[float]]) -> dict[str, Any]:
    days = sorted(cond_by_day.keys())
    if len(days) < 2:
        return {"ok": False}
    rows = []
    for held in days:
        vals = []
        for d, vs in cond_by_day.items():
            if d != held:
                vals.extend(vs)
        rows.append({"held_out": held, "mean": mean(vals)})
    signs = [1 if (r["mean"] or 0) > 0 else (-1 if (r["mean"] or 0) < 0 else 0) for r in rows]
    return {
        "ok": True,
        "rows": rows,
        "all_positive": all(s > 0 for s in signs),
        "all_negative": all(s < 0 for s in signs),
        "sign_flips": sum(1 for i in range(1, len(signs)) if signs[i] != signs[0]),
    }
