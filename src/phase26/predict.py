"""Chronological walk-forward predictive baselines (interpretable)."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    r2_score,
)

from phase14.constants import FOLDS
from phase14.data import fold_of
from phase26.constants import BASELINE_FEATURE_COLS, EVAL_SEED, PREDICT_TARGETS
from phase26.data import train_cutoff_for_fold
from phase26.outcomes import target_vector


def _xy(
    m5: dict,
    feats: dict[str, np.ndarray],
    outcomes: dict,
    indices: list[int],
    feature_names: list[str],
    target_id: str,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    rows = m5["rows"]
    y_all = target_vector(outcomes, target_id, len(m5["times"]))
    X_list = []
    y_list = []
    kept = []
    for i in indices:
        y = y_all[i]
        if not np.isfinite(y):
            continue
        vec = []
        ok = True
        for name in feature_names:
            if name in BASELINE_FEATURE_COLS:
                v = float(rows[i][name])
            else:
                v = float(feats[name][i])
            if not np.isfinite(v):
                ok = False
                break
            vec.append(v)
        if not ok:
            continue
        X_list.append(vec)
        y_list.append(float(y))
        kept.append(i)
    if not X_list:
        return np.zeros((0, len(feature_names))), np.zeros(0), []
    return np.asarray(X_list, dtype=float), np.asarray(y_list, dtype=float), kept


def _fit_predict(
    Xtr: np.ndarray,
    ytr: np.ndarray,
    Xte: np.ndarray,
    kind: str,
) -> np.ndarray:
    if kind == "classification":
        # map nan-free labels already; ensure 0/1
        clf = LogisticRegression(max_iter=500, random_state=EVAL_SEED)
        clf.fit(Xtr, ytr.astype(int))
        return clf.predict_proba(Xte)[:, 1]
    model = Ridge(alpha=1.0, random_state=EVAL_SEED)
    model.fit(Xtr, ytr)
    return model.predict(Xte)


def _metrics(kind: str, y_true: np.ndarray, y_hat: np.ndarray) -> dict[str, float]:
    if len(y_true) == 0:
        return {"n": 0}
    if kind == "classification":
        pred = (y_hat >= 0.5).astype(int)
        yt = y_true.astype(int)
        out = {
            "n": int(len(yt)),
            "accuracy": float(accuracy_score(yt, pred)),
            "brier": float(brier_score_loss(yt, y_hat)),
        }
        # log_loss needs both classes sometimes
        try:
            out["log_loss"] = float(log_loss(yt, np.clip(y_hat, 1e-6, 1 - 1e-6), labels=[0, 1]))
        except Exception:
            out["log_loss"] = float("nan")
        out["pos_rate"] = float(yt.mean())
        return out
    return {
        "n": int(len(y_true)),
        "mae": float(mean_absolute_error(y_true, y_hat)),
        "r2": float(r2_score(y_true, y_hat)) if len(y_true) > 1 else float("nan"),
        "corr": float(np.corrcoef(y_true, y_hat)[0, 1])
        if len(y_true) > 1 and float(np.std(y_true)) > 0 and float(np.std(y_hat)) > 0
        else float("nan"),
    }


def walk_forward_predict(
    m5: dict,
    feats: dict[str, np.ndarray],
    outcomes: dict,
    accepted_features: list[str],
    decision_indices: list[int],
) -> dict[str, Any]:
    times = m5["times"]
    results: dict[str, Any] = {}

    for spec in PREDICT_TARGETS:
        tid = spec["id"]
        kind = spec["kind"]
        fold_blocks = {}
        for fold_id in FOLDS:
            cutoff = train_cutoff_for_fold(fold_id)
            # Train on all past closed bars before purge cutoff (not only OOS grid).
            train_idx = [i for i, t in enumerate(times) if t <= cutoff]
            test_idx = [i for i in decision_indices if fold_of(times[i]) == fold_id]
            # embargo: drop train samples whose outcome window overlaps fold start
            # purge already encoded by cutoff = fold_start - 60m; additionally
            # drop train indices within last max_horizon of cutoff already by cutoff.
            base_names = list(BASELINE_FEATURE_COLS)
            ortho_names = base_names + list(accepted_features)

            Xb_tr, yb_tr, _ = _xy(m5, feats, outcomes, train_idx, base_names, tid)
            Xb_te, yb_te, _ = _xy(m5, feats, outcomes, test_idx, base_names, tid)
            Xo_tr, yo_tr, _ = _xy(m5, feats, outcomes, train_idx, ortho_names, tid)
            Xo_te, yo_te, _ = _xy(m5, feats, outcomes, test_idx, ortho_names, tid)

            block: dict[str, Any] = {
                "train_cutoff": cutoff,
                "n_train_base": int(len(yb_tr)),
                "n_test_base": int(len(yb_te)),
                "n_train_ortho": int(len(yo_tr)),
                "n_test_ortho": int(len(yo_te)),
            }
            if len(yb_tr) >= 50 and len(yb_te) >= 20 and (
                kind != "classification" or len(np.unique(yb_tr)) > 1
            ):
                hat_b = _fit_predict(Xb_tr, yb_tr, Xb_te, kind)
                block["baseline"] = _metrics(kind, yb_te, hat_b)
            else:
                block["baseline"] = {"n": int(len(yb_te)), "skipped": True}

            if (
                accepted_features
                and len(yo_tr) >= 50
                and len(yo_te) >= 20
                and (kind != "classification" or len(np.unique(yo_tr)) > 1)
            ):
                hat_o = _fit_predict(Xo_tr, yo_tr, Xo_te, kind)
                block["baseline_plus_orthogonal"] = _metrics(kind, yo_te, hat_o)
            else:
                block["baseline_plus_orthogonal"] = {
                    "n": int(len(yo_te)),
                    "skipped": True,
                    "reason": "insufficient_data_or_no_accepted_features",
                }

            # incremental comparison
            b = block["baseline"]
            o = block["baseline_plus_orthogonal"]
            if kind == "regression" and "mae" in b and "mae" in o:
                block["mae_improvement"] = float(b["mae"] - o["mae"])
                block["improved"] = bool(o["mae"] < b["mae"])
            elif kind == "classification" and "log_loss" in b and "log_loss" in o:
                block["log_loss_improvement"] = float(b["log_loss"] - o["log_loss"])
                block["improved"] = bool(o["log_loss"] < b["log_loss"])
            else:
                block["improved"] = False
            fold_blocks[fold_id] = block

        improved_folds = sum(1 for f in fold_blocks.values() if f.get("improved"))
        results[tid] = {
            "kind": kind,
            "folds": fold_blocks,
            "n_folds_improved": improved_folds,
            "all_folds_improved": improved_folds == len(FOLDS),
        }
    return results
