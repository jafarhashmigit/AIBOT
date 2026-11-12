"""Block-aware stats and multiple-testing helpers."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any

from phase42.constants import ALPHA, BONFERRONI_N


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def welch_t(a: list[float], b: list[float]) -> dict[str, Any]:
    """Approximate two-sample comparison; dates are dependent — treat as descriptive + bootstrap primary."""
    if len(a) < 5 or len(b) < 5:
        return {"ok": False, "reason": "small_n"}
    ma, mb = mean(a), mean(b)
    va = sum((x - ma) ** 2 for x in a) / max(1, len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / max(1, len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se == 0:
        return {"ok": False, "reason": "zero_se"}
    t = (ma - mb) / se
    # normal approx two-sided p
    # erf-based
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2))))
    return {"ok": True, "t": t, "p_approx": p, "mean_a": ma, "mean_b": mb, "effect": ma - mb}


def date_block_bootstrap_diff(
    cond_by_day: dict[str, list[float]],
    uncond_by_day: dict[str, list[float]],
    n_draws: int = 1500,
    seed: int = 42,
) -> dict[str, Any]:
    days = sorted(set(cond_by_day) | set(uncond_by_day))
    if len(days) < 2:
        return {"ok": False, "reason": "need>=2_dates"}
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_draws):
        sample = [days[rng.randrange(len(days))] for _ in range(len(days))]
        ca, ua = [], []
        for d in sample:
            ca.extend(cond_by_day.get(d) or [])
            ua.extend(uncond_by_day.get(d) or [])
        if ca and ua:
            diffs.append(sum(ca) / len(ca) - sum(ua) / len(ua))
    if not diffs:
        return {"ok": False, "reason": "empty"}
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[int(0.975 * len(diffs))]
    p_le0 = sum(1 for x in diffs if x <= 0) / len(diffs)
    alpha_b = ALPHA / BONFERRONI_N
    q = int(alpha_b * len(diffs))
    qh = int((1 - alpha_b) * len(diffs)) - 1
    return {
        "ok": True,
        "n_dates": len(days),
        "ci95_low": lo,
        "ci95_high": hi,
        "ci95_excludes_zero": lo > 0 or hi < 0,
        "prob_effect_le_0": p_le0,
        "bonferroni_alpha": alpha_b,
        "bonferroni_ci_low": diffs[max(0, q)],
        "bonferroni_ci_high": diffs[min(len(diffs) - 1, qh)],
        "bonferroni_excludes_zero": diffs[max(0, q)] > 0 or diffs[min(len(diffs) - 1, qh)] < 0,
        "mean_effect": sum(diffs) / len(diffs),
    }


def leave_one_date_out_effect(
    cond_by_day: dict[str, list[float]],
    uncond_by_day: dict[str, list[float]],
) -> dict[str, Any]:
    days = sorted(set(cond_by_day.keys()))
    if len(days) < 2:
        return {"ok": False}
    rows = []
    for held in days:
        ca, ua = [], []
        for d in days:
            if d == held:
                continue
            ca.extend(cond_by_day.get(d) or [])
            ua.extend(uncond_by_day.get(d) or [])
        eff = (sum(ca) / len(ca) - sum(ua) / len(ua)) if ca and ua else None
        rows.append({"held_out": held, "effect": eff})
    signs = [1 if (r["effect"] or 0) > 0 else (-1 if (r["effect"] or 0) < 0 else 0) for r in rows]
    return {
        "ok": True,
        "rows": rows,
        "all_positive": all(s > 0 for s in signs),
        "all_negative": all(s < 0 for s in signs),
        "sign_flips": sum(1 for i in range(1, len(signs)) if signs[i] != signs[0]),
    }


def group_by_day(pairs: list[tuple[str, float]]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for d, v in pairs:
        out[d].append(v)
    return dict(out)
