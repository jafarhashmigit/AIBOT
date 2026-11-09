"""Descriptive evaluation. Not used to retune the learner."""

from __future__ import annotations

import numpy as np

from phase3.nplib import day_cluster_bootstrap_mean
from phase9.constants import N_BOOT, SEED


def actions_from_records(records: list[dict], key: str = "final_decision") -> np.ndarray:
    return np.array([r[key] for r in records], dtype=object)


def prediction_quality(records: list[dict], eval_rows: list[dict]) -> dict:
    ev = {e["timestamp"]: e for e in eval_rows}
    out = {}
    for side, pkey, akey in (
        ("BUY", "pred_buy", "actual_net_r_BUY"),
        ("SELL", "pred_sell", "actual_net_r_SELL"),
    ):
        pred, actual = [], []
        for rec in records:
            if rec.get(pkey) is None:
                continue
            pred.append(float(rec[pkey]))
            actual.append(float(ev[rec["timestamp"]][akey]))
        if not pred:
            out[side] = {"n": 0, "note": "learner unavailable or no predictions"}
            continue
        p = np.array(pred, dtype=float)
        a = np.array(actual, dtype=float)
        err = p - a
        corr = float(np.corrcoef(p, a)[0, 1]) if len(p) > 1 and p.std() > 0 and a.std() > 0 else float("nan")
        out[side] = {
            "n": int(len(p)),
            "mae": float(np.mean(np.abs(err))),
            "rmse": float(np.sqrt(np.mean(err ** 2))),
            "corr": corr,
            "mean_predicted_r": float(p.mean()),
            "mean_realized_r": float(a.mean()),
            "label": "DESCRIPTIVE — NOT USED FOR OPTIMIZATION",
        }
    return out


def bootstrap_decision_r_diff(eval_rows: list[dict], a_actions: np.ndarray, b_actions: np.ndarray) -> dict:
    """Day-cluster bootstrap of mean(R_B - R_A) on decision-level R (WAIT=0)."""
    from phase3.decision_policy import realized_from_action
    r_a, _, _ = realized_from_action(eval_rows, a_actions)
    r_b, _, _ = realized_from_action(eval_rows, b_actions)
    r_a = np.where(a_actions == "WAIT", 0.0, r_a)
    r_b = np.where(b_actions == "WAIT", 0.0, r_b)
    delta = r_b - r_a
    times = [e["timestamp"] for e in eval_rows]
    boot = day_cluster_bootstrap_mean(times, delta, n_samples=N_BOOT, seed=SEED)
    return {
        "mean_difference_r": float(delta.mean()),
        "ci_low": boot["ci_low"],
        "ci_high": boot["ci_high"],
        "p_diff_le_0": boot["p_mean_le_0"],
        "n_samples": N_BOOT,
        "seed": SEED,
        "method": "day_cluster",
        "n_days": boot.get("n_days"),
        "label": "DESCRIPTIVE — NOT USED FOR OPTIMIZATION",
        "comparison": "Phase9_experience_learner_final minus frozen_phase6_agent_final",
    }


def fold_counts(records: list[dict]) -> dict:
    out = {}
    for fold in ("WF1", "WF2", "WF3"):
        part = [r for r in records if r.get("fold_id") == fold]
        acts = [r["final_decision"] for r in part]
        raw = [r["raw_decision"] for r in part]
        ns = [r["n_experiences"] for r in part]
        out[fold] = {
            "decision_count": len(part),
            "final_BUY": acts.count("BUY"),
            "final_SELL": acts.count("SELL"),
            "final_WAIT": acts.count("WAIT"),
            "raw_BUY": raw.count("BUY"),
            "raw_SELL": raw.count("SELL"),
            "raw_WAIT": raw.count("WAIT"),
            "experience_n_min": min(ns) if ns else 0,
            "experience_n_max": max(ns) if ns else 0,
            "n_learner_source": sum(1 for r in part if r["source"] == "experience_ridge"),
        }
    return out
