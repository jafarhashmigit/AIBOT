"""Day-block bootstrap for mean net R — preserves temporal dependence."""

from __future__ import annotations

import random
from typing import Any

from phase36.progress import write_json


def day_block_bootstrap(
    trades: list[dict[str, Any]],
    *,
    n_draws: int = 2000,
    seed: int = 36,
) -> dict[str, Any]:
    """Resample days with replacement; recompute mean net R of resolved trades."""
    resolved = [t for t in trades if t.get("status") in {"PASS", "FAIL", "TIMEOUT"}]
    by_day: dict[str, list[float]] = {}
    for t in resolved:
        by_day.setdefault(str(t.get("day")), []).append(float(t["net_r"]))
    days = sorted(by_day.keys())
    if not days:
        report = {"ok": False, "reason": "no_resolved_trades", "n_days": 0}
        write_json("bootstrap.json", report)
        return report

    rng = random.Random(seed)
    means = []
    for _ in range(n_draws):
        sample_rs: list[float] = []
        for _d in range(len(days)):
            day = days[rng.randrange(len(days))]
            sample_rs.extend(by_day[day])
        if sample_rs:
            means.append(sum(sample_rs) / len(sample_rs))
        else:
            means.append(0.0)
    means.sort()
    lo = means[int(0.025 * (len(means) - 1))]
    hi = means[int(0.975 * (len(means) - 1))]
    p_le_0 = sum(1 for m in means if m <= 0) / len(means)

    # Positive-day ratio
    day_means = {d: sum(rs) / len(rs) for d, rs in by_day.items() if rs}
    pos_days = sum(1 for m in day_means.values() if m > 0)
    pos_ratio = pos_days / len(day_means) if day_means else 0.0

    # Leave-one-day-out stability
    lodo = []
    for hold in days:
        rs = []
        for d, vals in by_day.items():
            if d == hold:
                continue
            rs.extend(vals)
        if rs:
            lodo.append({"held_out": hold, "mean_r": sum(rs) / len(rs), "n": len(rs)})
    sign_flips = sum(1 for x in lodo if (x["mean_r"] <= 0))

    report = {
        "ok": True,
        "method": "day_block_bootstrap",
        "n_draws": n_draws,
        "seed": seed,
        "n_days": len(days),
        "n_resolved": len(resolved),
        "observed_mean_r": (sum(float(t["net_r"]) for t in resolved) / len(resolved)),
        "ci95_low": lo,
        "ci95_high": hi,
        "ci95_excludes_zero": lo > 0 or hi < 0,
        "prob_mean_r_le_0": p_le_0,
        "positive_day_ratio": pos_ratio,
        "positive_days": pos_days,
        "day_means": day_means,
        "leave_one_day_out": lodo,
        "leave_one_day_out_nonpositive_count": sign_flips,
        "dependent_on_one_exceptional_day": sign_flips > 0 and (sum(float(t["net_r"]) for t in resolved) / len(resolved)) > 0,
    }
    write_json("bootstrap.json", report)
    return report
