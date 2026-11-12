"""Predictive value vs trading profitability using Phase2 OOS predictions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from phase31.constants import HOLDOUT_NAME, OOS_PRED_PATH, RESEARCH_CUTOFF_UTC


def _safe_logloss(y_true: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    # three-class: TP/SL/TIME one-hot via actual_exit_reason
    return float(-np.mean(np.log(p)))


def run_prediction_diagnostics() -> dict[str, Any]:
    if HOLDOUT_NAME in str(OOS_PRED_PATH):
        raise RuntimeError("HARD FAILURE: holdout path referenced")
    if not OOS_PRED_PATH.exists():
        return {"ok": False, "error": "phase2_oos_predictions missing"}

    df = pd.read_csv(OOS_PRED_PATH)
    df["decision_time"] = pd.to_datetime(df["decision_time"])
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)
    df = df[df["decision_time"] <= cutoff].copy()

    # Directional: treat pred class as argmax of rf probs for exit reason
    for pref in ("rf", "logreg"):
        cols = [f"p_tp_{pref}", f"p_sl_{pref}", f"p_time_{pref}"]
        if not all(c in df.columns for c in cols):
            continue
    # Primary classifier
    pcols = ["p_tp_rf", "p_sl_rf", "p_time_rf"]
    probs = df[pcols].to_numpy(dtype=float)
    pred = np.array(["TP", "SL", "TIME"])[probs.argmax(axis=1)]
    actual = df["actual_exit_reason"].astype(str).to_numpy()
    acc = float((pred == actual).mean()) if len(df) else None

    # Balanced accuracy
    labels = ["TP", "SL", "TIME"]
    recalls = []
    for lab in labels:
        mask = actual == lab
        if mask.sum() == 0:
            continue
        recalls.append(float((pred[mask] == lab).mean()))
    bal_acc = float(np.mean(recalls)) if recalls else None

    # Brier (multiclass)
    y = np.zeros_like(probs)
    for i, lab in enumerate(labels):
        y[:, i] = (actual == lab).astype(float)
    brier = float(np.mean(np.sum((probs - y) ** 2, axis=1)))

    # Regression predictive value vs net R
    if "pred_r_rf" in df.columns and "actual_net_r" in df.columns:
        pr = df["pred_r_rf"].to_numpy(dtype=float)
        ar = df["actual_net_r"].to_numpy(dtype=float)
        ok = np.isfinite(pr) & np.isfinite(ar)
        if ok.sum() > 10:
            corr = float(np.corrcoef(pr[ok], ar[ok])[0, 1])
            # Buckets by predicted R
            q = pd.qcut(pr[ok], q=5, duplicates="drop")
            bucket = (
                pd.DataFrame({"pred": pr[ok], "actual": ar[ok], "bucket": q})
                .groupby("bucket", observed=True)["actual"]
                .agg(["count", "mean"])
                .reset_index()
            )
            bucket_rows = [
                {"bucket": str(r["bucket"]), "n": int(r["count"]), "mean_actual_net_r": float(r["mean"])}
                for _, r in bucket.iterrows()
            ]
        else:
            corr, bucket_rows = None, []
    else:
        corr, bucket_rows = None, []

    # Hard label directional accuracy vs chance (TP vs not) is not the same as BUY/SELL
    chance = float(max((actual == lab).mean() for lab in labels)) if len(df) else None

    return {
        "holdout_opened": False,
        "n_oos_rows_le_cutoff": int(len(df)),
        "exit_reason_accuracy_rf": acc,
        "balanced_accuracy_rf": bal_acc,
        "brier_rf": brier,
        "majority_class_rate": chance,
        "pred_r_rf_corr_actual_net_r": corr,
        "conditional_mean_net_r_by_pred_r_bucket": bucket_rows,
        "mean_actual_net_r": float(df["actual_net_r"].mean()) if len(df) else None,
        "interpretation": (
            "If classification accuracy ≈ majority baseline and pred_r correlation is weak, "
            "models fail to predict monetizable outcomes. If correlation exists but mean net R "
            "remains ≤0 after costs, signal is not executable profit under current barriers."
        ),
        "ok": True,
    }
