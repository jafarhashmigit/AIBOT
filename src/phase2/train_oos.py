"""Walk-forward OOS predictions. Models see only earlier training folds."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from evaluation.constants import TIME_FORMAT
from phase2.constants import (
    FEATURE_ALLOWLIST,
    FEATURE_VERSION,
    LOGREG_PARAMS,
    MODELS_DIR,
    OUTCOME_CLASSES,
    RF_CLF_PARAMS,
    RF_REG_PARAMS,
    RIDGE_PARAMS,
    SEED,
    SIDES,
)


def _X(df: pd.DataFrame) -> np.ndarray:
    return df.loc[:, list(FEATURE_ALLOWLIST)].to_numpy(dtype=float)


def _proba(model, X, classes=OUTCOME_CLASSES) -> np.ndarray:
    raw = model.predict_proba(X)
    out = np.zeros((len(X), len(classes)), dtype=float)
    index = {c: i for i, c in enumerate(model.classes_)}
    for j, name in enumerate(classes):
        if name in index:
            out[:, j] = raw[:, index[name]]
    return out


def _save(obj, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, path)
    return str(path)


def train_fold(train: pd.DataFrame, eval_df: pd.DataFrame, fold_id: str,
               generated_at: str) -> tuple[pd.DataFrame, list[dict]]:
    rows, registry = [], []
    train_end = train["decision_time"].max()
    for side in SIDES:
        tr = train[train["side"] == side]
        ev = eval_df[eval_df["side"] == side]
        Xtr, Xev = _X(tr), _X(ev)
        y_cls = tr["exit_reason"].to_numpy()
        y_r = tr["net_r"].to_numpy(dtype=float)

        scaler = StandardScaler().fit(Xtr)
        Xs_tr, Xs_ev = scaler.transform(Xtr), scaler.transform(Xev)
        scaler_path = _save(scaler, MODELS_DIR / f"scaler_{side}_{fold_id}.pkl")

        # --- classification ---
        prior = {c: float((y_cls == c).mean()) for c in OUTCOME_CLASSES}
        logreg = LogisticRegression(**LOGREG_PARAMS).fit(Xs_tr, y_cls)
        rf_clf = RandomForestClassifier(**RF_CLF_PARAMS).fit(Xtr, y_cls)
        p_prior = np.tile([prior[c] for c in OUTCOME_CLASSES], (len(ev), 1))
        p_logreg = _proba(logreg, Xs_ev)
        p_rf = _proba(rf_clf, Xev)

        # --- regression ---
        const = float(y_r.mean())
        ridge = Ridge(**RIDGE_PARAMS).fit(Xs_tr, y_r)
        rf_reg = RandomForestRegressor(**RF_REG_PARAMS).fit(Xtr, y_r)
        r_const = np.full(len(ev), const)
        r_ridge = ridge.predict(Xs_ev)
        r_rf = rf_reg.predict(Xev)

        logreg_path = _save(logreg, MODELS_DIR / f"logreg_{side}_{fold_id}.pkl")
        rf_clf_path = _save(rf_clf, MODELS_DIR / f"rfclf_{side}_{fold_id}.pkl")
        ridge_path = _save(ridge, MODELS_DIR / f"ridge_{side}_{fold_id}.pkl")
        rf_reg_path = _save(rf_reg, MODELS_DIR / f"rfreg_{side}_{fold_id}.pkl")

        for i in range(len(ev)):
            rec = ev.iloc[i]
            rows.append({
                "decision_time": rec["decision_time"].strftime(TIME_FORMAT),
                "side": side,
                "fold_id": fold_id,
                "training_period_end": train_end.strftime(TIME_FORMAT),
                "prediction_generated_at_utc": generated_at,
                "p_tp_prior": p_prior[i, 0],
                "p_sl_prior": p_prior[i, 1],
                "p_time_prior": p_prior[i, 2],
                "p_tp_logreg": p_logreg[i, 0],
                "p_sl_logreg": p_logreg[i, 1],
                "p_time_logreg": p_logreg[i, 2],
                "p_tp_rf": p_rf[i, 0],
                "p_sl_rf": p_rf[i, 1],
                "p_time_rf": p_rf[i, 2],
                "pred_r_const": r_const[i],
                "pred_r_ridge": r_ridge[i],
                "pred_r_rf": r_rf[i],
                "actual_exit_reason": rec["exit_reason"],
                "actual_net_r": rec["net_r"],
                "actual_net_pnl": rec["net_pnl"],
                "primary_clf_model_id": f"rfclf_{side}_{fold_id}",
                "primary_reg_model_id": f"rfreg_{side}_{fold_id}",
                "feature_version": FEATURE_VERSION,
            })

        registry.extend([
            {"model_id": f"prior_{side}_{fold_id}", "type": "class_prior", "side": side, "fold_id": fold_id,
             "params": prior, "artifact": None, "scaler": None},
            {"model_id": f"logreg_{side}_{fold_id}", "type": "logistic_regression", "side": side, "fold_id": fold_id,
             "params": LOGREG_PARAMS, "artifact": logreg_path, "scaler": scaler_path},
            {"model_id": f"rfclf_{side}_{fold_id}", "type": "random_forest_classifier", "side": side, "fold_id": fold_id,
             "params": RF_CLF_PARAMS, "artifact": rf_clf_path, "scaler": None},
            {"model_id": f"const_{side}_{fold_id}", "type": "constant_mean_r", "side": side, "fold_id": fold_id,
             "params": {"mean_r": const}, "artifact": None, "scaler": None},
            {"model_id": f"ridge_{side}_{fold_id}", "type": "ridge_regression", "side": side, "fold_id": fold_id,
             "params": RIDGE_PARAMS, "artifact": ridge_path, "scaler": scaler_path},
            {"model_id": f"rfreg_{side}_{fold_id}", "type": "random_forest_regressor", "side": side, "fold_id": fold_id,
             "params": RF_REG_PARAMS, "artifact": rf_reg_path, "scaler": None},
        ])
    preds = pd.DataFrame(rows).sort_values(["decision_time", "side"]).reset_index(drop=True)
    for item in registry:
        item["training_period_end"] = train_end.strftime(TIME_FORMAT)
        item["seed"] = SEED
        item["n_train"] = int((train["side"] == item["side"]).sum())
        item["n_eval"] = int((eval_df["side"] == item["side"]).sum())
        item["generated_at_utc"] = generated_at
    return preds, registry


def run_walk_forward(folds: list[dict]) -> tuple[pd.DataFrame, list[dict]]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_preds, all_reg = [], []
    for fold in folds:
        print(f"{fold['fold_id']}: train {fold['train_rows']} eval {fold['eval_rows']}")
        preds, reg = train_fold(fold["train"], fold["eval"], fold["fold_id"], generated_at)
        all_preds.append(preds)
        all_reg.extend(reg)
    return pd.concat(all_preds, ignore_index=True), all_reg
