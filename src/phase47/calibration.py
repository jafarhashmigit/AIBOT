"""Probability calibration metrics on out-of-fold predictions only."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def brier_score(y_true: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y_true) ** 2))


def log_loss(y_true: np.ndarray, p: np.ndarray, eps: float = 1e-12) -> float:
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p)))


def expected_calibration_error(y_true: np.ndarray, p: np.ndarray, n_bins: int = 10) -> dict[str, Any]:
    if len(y_true) == 0:
        return {"ece": None, "bins": [], "ok": False, "reason": "empty"}
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    rows = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        if not np.any(mask):
            rows.append({"lo": float(lo), "hi": float(hi), "n": 0, "conf": None, "acc": None})
            continue
        conf = float(np.mean(p[mask]))
        acc = float(np.mean(y_true[mask]))
        w = float(np.mean(mask))
        ece += w * abs(acc - conf)
        rows.append({"lo": float(lo), "hi": float(hi), "n": int(mask.sum()), "conf": conf, "acc": acc})
    return {"ece": float(ece), "bins": rows, "ok": True, "n": int(len(y_true))}


def regression_errors(y: np.ndarray, yhat: np.ndarray) -> dict[str, Any]:
    if len(y) == 0:
        return {"mae": None, "rmse": None, "bias": None}
    err = yhat - y
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(math.sqrt(np.mean(err**2))),
        "bias": float(np.mean(err)),
        "corr": float(np.corrcoef(y, yhat)[0, 1]) if len(y) > 2 else None,
    }


def evaluate_predictions(preds: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    if not preds:
        return {"label": label, "ok": False, "reason": "no_predictions", "n": 0}
    y = np.array([1.0 if float(p["actual_net_r"]) > 0 else 0.0 for p in preds])
    p = np.array([float(p["p_positive_net_r"]) for p in preds])
    ev = np.array([float(p["expected_net_r"]) for p in preds])
    direct = np.array([float(p["expected_net_r_direct"]) for p in preds])
    actual = np.array([float(p["actual_net_r"]) for p in preds])

    # Conditional payoff actual vs predicted among realized pos/neg
    pos_mask = actual > 0
    neg_mask = actual <= 0
    cond = {
        "pos_actual_mean": float(np.mean(actual[pos_mask])) if np.any(pos_mask) else None,
        "pos_pred_mean": float(np.mean([float(x["expected_positive_net_r"]) for x in preds if float(x["actual_net_r"]) > 0]))
        if np.any(pos_mask)
        else None,
        "neg_actual_mean": float(np.mean(actual[neg_mask])) if np.any(neg_mask) else None,
        "neg_pred_mean": float(np.mean([float(x["expected_negative_net_r"]) for x in preds if float(x["actual_net_r"]) <= 0]))
        if np.any(neg_mask)
        else None,
    }

    cal = expected_calibration_error(y, p)
    return {
        "label": label,
        "ok": True,
        "n": len(preds),
        "base_rate_positive": float(np.mean(y)),
        "brier": brier_score(y, p),
        "log_loss": log_loss(y, p),
        "calibration": cal,
        "ev_decomp_error": regression_errors(actual, ev),
        "ev_direct_error": regression_errors(actual, direct),
        "conditional_payoff": cond,
        "mean_actual_net_r": float(np.mean(actual)),
        "mean_predicted_ev": float(np.mean(ev)),
        "mean_predicted_direct": float(np.mean(direct)),
    }


def date_block_ci(preds: list[dict[str, Any]], field: str = "actual_net_r", n_draws: int = 800, seed: int = 47) -> dict[str, Any]:
    import random
    from collections import defaultdict

    by: dict[str, list[float]] = defaultdict(list)
    for p in preds:
        by[str(p["day"])].append(float(p[field]))
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
    return {
        "ok": True,
        "n_dates": len(days),
        "ci95_low": means[int(0.025 * len(means))],
        "ci95_high": means[int(0.975 * len(means))],
        "mean": sum(means) / len(means),
    }
