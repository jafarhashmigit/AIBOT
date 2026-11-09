"""Slice economics, FDR, and the Phase 4 conditional-edge gate."""

from __future__ import annotations

import numpy as np

from phase3.nplib import day_cluster_bootstrap_mean, max_drawdown, profit_factor, win_rate
from phase4.constants import FDR_Q, GATE, MIN_SLICE_N, SEED, SPREAD_FLOOR_USD, SPREAD_STRESS


def _metrics(r: np.ndarray, pnl: np.ndarray, times: list) -> dict:
    n = int(len(r))
    if n == 0:
        return {
            "n": 0, "mean_r": float("nan"), "median_r": float("nan"), "net_r": 0.0,
            "net_pnl": 0.0, "profit_factor": float("nan"), "win_rate": float("nan"),
            "max_drawdown_usd": 0.0, "bootstrap": {
                "mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "p_mean_le_0": float("nan"), "n_days": 0, "n_samples": 2000, "seed": SEED,
                "method": "day_cluster"},
        }
    boot = day_cluster_bootstrap_mean(times, r, n_samples=2000, seed=SEED)
    return {
        "n": n,
        "mean_r": float(r.mean()),
        "median_r": float(np.median(r)),
        "net_r": float(r.sum()),
        "net_pnl": float(pnl.sum()),
        "profit_factor": profit_factor(pnl),
        "win_rate": win_rate(pnl),
        "max_drawdown_usd": max_drawdown(pnl),
        "bootstrap": boot,
    }


def slice_unconditional(rows: list[dict], side: str, key: str, value: str) -> dict:
    part = [r for r in rows if r.get(key) == value]
    r = np.array([p[f"actual_net_r_{side}"] for p in part], dtype=float)
    pnl = np.array([p[f"actual_net_pnl_{side}"] for p in part], dtype=float)
    times = [p["decision_time"] for p in part]
    by_fold = {}
    for fold in dict.fromkeys(p["fold_id"] for p in part):
        sub = [p for p in part if p["fold_id"] == fold]
        rr = np.array([p[f"actual_net_r_{side}"] for p in sub], dtype=float)
        pp = np.array([p[f"actual_net_pnl_{side}"] for p in sub], dtype=float)
        tt = [p["decision_time"] for p in sub]
        by_fold[fold] = _metrics(rr, pp, tt)
    out = _metrics(r, pnl, times)
    out["side"] = side
    out["family"] = key
    out["level"] = value
    out["slice_id"] = f"{key}:{value}:{side}"
    out["by_fold"] = by_fold
    return out


def stress_mean_r(rows: list[dict], side: str, key: str, value: str, mult: float) -> float:
    extra = (mult - 1.0) * SPREAD_FLOOR_USD
    rs = []
    for p in rows:
        if p.get(key) != value:
            continue
        pnl = p[f"actual_net_pnl_{side}"]
        r = p[f"actual_net_r_{side}"]
        if abs(r) < 1e-12:
            continue
        risk = pnl / r
        if risk <= 0 or not np.isfinite(risk):
            continue
        rs.append((pnl - extra) / risk)
    return float(np.mean(rs)) if rs else float("nan")


def bh_fdr(items: list[dict], q: float = FDR_Q) -> list[dict]:
    eligible = [x for x in items if x["n"] >= MIN_SLICE_N and np.isfinite(x["bootstrap"].get("p_mean_le_0", float("nan")))]
    m = len(eligible)
    if m == 0:
        for x in items:
            x["fdr_tested"] = False
            x["fdr_pass"] = False
        return items
    order = sorted(range(m), key=lambda i: eligible[i]["bootstrap"]["p_mean_le_0"])
    cutoff = -1
    for rank, i in enumerate(order, start=1):
        p = eligible[i]["bootstrap"]["p_mean_le_0"]
        if p <= q * rank / m:
            cutoff = rank
    passing_ids = set()
    if cutoff >= 0:
        for rank, i in enumerate(order, start=1):
            if rank <= cutoff:
                passing_ids.add(eligible[i]["slice_id"])
    for x in items:
        x["fdr_tested"] = x["slice_id"] in {e["slice_id"] for e in eligible}
        x["fdr_family_size"] = m
        x["fdr_pass"] = x["slice_id"] in passing_ids
        x["fdr_q"] = q
    return items


def gate_slice(rec: dict) -> dict:
    folds = rec.get("by_fold") or {}
    fold_means = {k: v.get("mean_r") for k, v in folds.items()}
    finite = [v for v in fold_means.values() if v is not None and np.isfinite(v)]
    both_pos = len(finite) >= 2 and all(v > 0 for v in finite)
    per_fold_n_ok = len(folds) >= 2 and all(v.get("n", 0) >= GATE["min_per_fold"] for v in folds.values())
    ci_low = rec["bootstrap"].get("ci_low")
    criteria = {
        "pooled_n": rec["n"] >= GATE["min_pooled"],
        "per_fold_n": per_fold_n_ok,
        "pooled_mean_r_positive": bool(np.isfinite(rec["mean_r"]) and rec["mean_r"] > 0),
        "both_outer_folds_positive": bool(both_pos),
        "ci_low_above_zero": bool(ci_low is not None and np.isfinite(ci_low) and ci_low > GATE["ci_low_must_exceed"]),
        "fdr_pass": bool(rec.get("fdr_pass")),
        "spread_x1_5_positive": bool(np.isfinite(rec.get("stress_mean_r_x1_5", float("nan")))
                                     and rec.get("stress_mean_r_x1_5") > 0),
    }
    return {
        "passed": all(criteria.values()),
        "criteria": criteria,
        "fold_mean_r": fold_means,
        "promising": bool(
            criteria["pooled_mean_r_positive"]
            and criteria["both_outer_folds_positive"]
            and rec["n"] >= GATE["min_pooled"]
            and not criteria["ci_low_above_zero"]
        ),
    }
