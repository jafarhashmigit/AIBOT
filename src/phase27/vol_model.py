"""Walk-forward predicted fwd_vol_12 (decision-time only)."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import mean_absolute_error, r2_score

from phase14.constants import FOLDS
from phase14.data import fold_of
from phase26.constants import BASELINE_FEATURE_COLS
from phase26.data import train_cutoff_for_fold
from phase26.outcomes import target_vector
from phase27.constants import EVAL_SEED, REGIME_METHOD, VOL_FEATURE_SET


def _row_vec(m5: dict, feats: dict[str, np.ndarray], i: int, names: tuple[str, ...]) -> np.ndarray | None:
    rows = m5["rows"]
    vec = []
    for name in names:
        if name in BASELINE_FEATURE_COLS:
            v = float(rows[i][name])
        else:
            v = float(feats[name][i])
        if not np.isfinite(v):
            return None
        vec.append(v)
    return np.asarray(vec, dtype=float)


def _xy(m5, feats, y_all, indices, names):
    X, y, kept = [], [], []
    for i in indices:
        if not np.isfinite(y_all[i]):
            continue
        v = _row_vec(m5, feats, i, names)
        if v is None:
            continue
        X.append(v)
        y.append(float(y_all[i]))
        kept.append(i)
    if not X:
        return np.zeros((0, len(names))), np.zeros(0), []
    return np.asarray(X), np.asarray(y), kept


def tertile_cuts(values: np.ndarray) -> tuple[float, float]:
    xs = values[np.isfinite(values)]
    if len(xs) < 30:
        return float("nan"), float("nan")
    return float(np.quantile(xs, 1 / 3)), float(np.quantile(xs, 2 / 3))


def assign_regime(pred: float, lo: float, hi: float) -> str:
    if not np.isfinite(pred) or not np.isfinite(lo) or not np.isfinite(hi):
        return "unknown"
    if pred <= lo:
        return "low"
    if pred <= hi:
        return "medium"
    return "high"


def build_oof_vol_predictions(
    m5: dict,
    feats: dict[str, np.ndarray],
    outcomes: dict,
    decision_indices: list[int],
) -> dict[str, Any]:
    """
    For each fold:
      - train Ridge on all bars <= purge cutoff (baseline+accepted features)
      - predict fwd_vol_12 on fold decision indices
      - tertile cuts from *train predicted* values (not realized future vol)
    Also audit baseline-only vs full feature set MAE on each fold.
    """
    times = m5["times"]
    y_all = target_vector(outcomes, "fwd_vol_12", len(times))
    names_full = VOL_FEATURE_SET
    names_base = tuple(BASELINE_FEATURE_COLS)

    pred_by_time: dict[str, float] = {}
    regime_by_time: dict[str, str] = {}
    fold_audit: dict[str, Any] = {}

    for fold_id in FOLDS:
        cutoff = train_cutoff_for_fold(fold_id)
        train_idx = [i for i, t in enumerate(times) if t <= cutoff]
        test_idx = [i for i in decision_indices if fold_of(times[i]) == fold_id]

        Xtr_f, ytr_f, _ = _xy(m5, feats, y_all, train_idx, names_full)
        Xte_f, yte_f, kept_te = _xy(m5, feats, y_all, test_idx, names_full)
        Xtr_b, ytr_b, _ = _xy(m5, feats, y_all, train_idx, names_base)
        Xte_b, yte_b, _ = _xy(m5, feats, y_all, test_idx, names_base)

        block: dict[str, Any] = {
            "train_cutoff": cutoff,
            "n_train_full": int(len(ytr_f)),
            "n_test_full": int(len(yte_f)),
            "regime_method": REGIME_METHOD,
        }
        if len(ytr_f) < 50 or len(yte_f) < 20:
            block["skipped"] = True
            fold_audit[fold_id] = block
            continue

        model_f = Ridge(alpha=1.0, random_state=EVAL_SEED).fit(Xtr_f, ytr_f)
        hat_te_f = model_f.predict(Xte_f)
        hat_tr_f = model_f.predict(Xtr_f)
        lo, hi = tertile_cuts(hat_tr_f)
        block["tertile_cuts_predicted_train"] = {"p33": lo, "p67": hi}

        model_b = Ridge(alpha=1.0, random_state=EVAL_SEED).fit(Xtr_b, ytr_b)
        hat_te_b = model_b.predict(Xte_b)

        block["baseline"] = {
            "mae": float(mean_absolute_error(yte_b, hat_te_b)),
            "r2": float(r2_score(yte_b, hat_te_b)),
            "n": int(len(yte_b)),
        }
        block["baseline_plus_ortho"] = {
            "mae": float(mean_absolute_error(yte_f, hat_te_f)),
            "r2": float(r2_score(yte_f, hat_te_f)),
            "n": int(len(yte_f)),
        }
        block["mae_improvement"] = block["baseline"]["mae"] - block["baseline_plus_ortho"]["mae"]
        block["improved"] = bool(block["mae_improvement"] > 0)

        # High/med/low classification of realized vol using predicted tertiles (diagnostics)
        # Class labels on realized y for calibration-style accuracy of regime assignment
        y_reg = np.array([assign_regime(v, lo, hi) for v in yte_f], dtype=object)
        p_reg = np.array([assign_regime(v, lo, hi) for v in hat_te_f], dtype=object)
        # Map to ordinal for crude accuracy of tercile match
        block["regime_agreement_rate"] = float(np.mean(y_reg == p_reg))

        # 3-class logistic on predicted features? Keep simple: use continuous Ridge + tertiles.
        # Also train ordinal-ish 3-way using realized train tertiles of y for class target (audit only)
        y_lo, y_hi = tertile_cuts(ytr_f)
        ytr_cls = np.array([0 if v <= y_lo else (1 if v <= y_hi else 2) for v in ytr_f])
        yte_cls = np.array([0 if v <= y_lo else (1 if v <= y_hi else 2) for v in yte_f])
        if len(np.unique(ytr_cls)) == 3:
            clf = LogisticRegression(max_iter=800, random_state=EVAL_SEED)
            clf.fit(Xtr_f, ytr_cls)
            pred_cls = clf.predict(Xte_f)
            block["vol_class_accuracy"] = float(np.mean(pred_cls == yte_cls))
        else:
            block["vol_class_accuracy"] = float("nan")

        for j, i in enumerate(kept_te):
            t = times[i]
            pred_by_time[t] = float(hat_te_f[j])
            regime_by_time[t] = assign_regime(float(hat_te_f[j]), lo, hi)

        fold_audit[fold_id] = block

    n_imp = sum(1 for f in fold_audit.values() if f.get("improved"))
    return {
        "pred_vol_by_time": pred_by_time,
        "regime_by_time": regime_by_time,
        "fold_audit": fold_audit,
        "n_folds_improved": n_imp,
        "all_folds_improved": n_imp == 3,
        "independent_verify_note": (
            "Recomputed Ridge walk-forward fwd_vol_12 using Phase 26 accepted features; "
            "regime cuts from train predicted tertiles only."
        ),
    }
