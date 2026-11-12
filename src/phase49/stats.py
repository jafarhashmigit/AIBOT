"""Date-block bootstrap, permutation, LODO — treat dates as blocks."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from phase49.constants import ALPHA, BONFERRONI_N, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def date_block_bootstrap(
    pairs: list[tuple[str, float]],
    *,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
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
        vals: list[float] = []
        for d in sample:
            vals.extend(by[d])
        if vals:
            means.append(sum(vals) / len(vals))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    alpha_b = ALPHA / BONFERRONI_N
    q = max(0, int(alpha_b * len(means)))
    qh = min(len(means) - 1, int((1 - alpha_b) * len(means)) - 1)
    return {
        "ok": True,
        "n_dates": len(days),
        "mean": sum(means) / len(means),
        "ci95_low": lo,
        "ci95_high": hi,
        "ci95_excludes_zero": lo > 0 or hi < 0,
        "bonferroni_alpha": alpha_b,
        "bonferroni_ci_low": means[q],
        "bonferroni_ci_high": means[qh],
        "bonferroni_excludes_zero": means[q] > 0 or means[qh] < 0,
        "prob_mean_le_0": sum(1 for m in means if m <= 0) / len(means),
    }


def leave_one_date_out(pairs: list[tuple[str, float]]) -> dict[str, Any]:
    by: dict[str, list[float]] = defaultdict(list)
    for d, v in pairs:
        by[d].append(v)
    days = sorted(by)
    if len(days) < 3:
        return {"ok": False, "reason": "need>=3_dates"}
    rows = []
    for held in days:
        vals = []
        for d, vs in by.items():
            if d != held:
                vals.extend(vs)
        rows.append({"held_out": held, "mean": mean(vals)})
    signs = [1 if (r["mean"] or 0) > 0 else (-1 if (r["mean"] or 0) < 0 else 0) for r in rows]
    return {
        "ok": True,
        "rows": rows,
        "all_positive": all(s > 0 for s in signs),
        "sign_flips": sum(1 for i in range(1, len(signs)) if signs[i] != signs[0]),
        "frac_positive": sum(1 for s in signs if s > 0) / len(signs),
    }


def block_permutation_pvalue(
    selected: list[tuple[str, float]],
    universe: list[tuple[str, float]],
    *,
    n_perm: int = 500,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Permute labels within date blocks: is selected mean unusual vs same-size draws?"""
    by_u: dict[str, list[float]] = defaultdict(list)
    for d, v in universe:
        by_u[d].append(v)
    by_s: dict[str, list[float]] = defaultdict(list)
    for d, v in selected:
        by_s[d].append(v)
    obs = mean([v for _, v in selected])
    if obs is None:
        return {"ok": False}
    rng = random.Random(seed)
    # For each date, draw same count as selected from universe
    counts = {d: len(vs) for d, vs in by_s.items()}
    null = []
    for _ in range(n_perm):
        vals = []
        for d, n in counts.items():
            pool = by_u.get(d) or []
            if len(pool) < n or n == 0:
                continue
            vals.extend(rng.sample(pool, n) if n < len(pool) else pool)
        if vals:
            null.append(sum(vals) / len(vals))
    if not null:
        return {"ok": False}
    # one-sided: P(null >= obs) if obs>0 else P(null <= obs)
    if obs >= 0:
        p = sum(1 for x in null if x >= obs) / len(null)
    else:
        p = sum(1 for x in null if x <= obs) / len(null)
    return {"ok": True, "observed_mean": obs, "perm_pvalue": p, "n_perm": len(null)}
