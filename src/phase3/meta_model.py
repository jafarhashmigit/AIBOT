"""Simple meta-models trained on inner OOS predictions only."""

from __future__ import annotations

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from phase3.baselines import baseline_a_wait
from phase3.constants import (
    DECISION_FEATURE_ALLOWLIST,
    LOGREG_PARAMS,
    META_TAU_CANDIDATES,
    MODELS_DIR,
    RIDGE_PARAMS,
    SIDES,
)
from phase3.decision_policy import decide_batch, select_threshold
from phase3.nplib import col


def _X(rows: list[dict]) -> np.ndarray:
    return np.column_stack([col(rows, c) for c in DECISION_FEATURE_ALLOWLIST])


def fit_meta(inner: list[dict], nested_id: str) -> dict:
    X = _X(inner)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    scaler_path = MODELS_DIR / f"scaler_{nested_id}.pkl"
    joblib.dump(scaler, scaler_path)
    models = {"scaler": scaler, "scaler_path": str(scaler_path), "ok": True, "notes": []}
    for side in SIDES:
        y_r = col(inner, f"actual_net_r_{side}")
        y_pos = (y_r > 0).astype(int)
        ridge = Ridge(**RIDGE_PARAMS).fit(Xs, y_r)
        ridge_path = MODELS_DIR / f"ridge_{side}_{nested_id}.pkl"
        joblib.dump(ridge, ridge_path)
        models[f"ridge_{side}"] = ridge
        models[f"ridge_{side}_path"] = str(ridge_path)
        if y_pos.min() == y_pos.max():
            models["ok"] = False
            models["notes"].append(f"{side}: logistic skipped, single class in inner labels")
            models[f"logreg_{side}"] = None
        else:
            logreg = LogisticRegression(**LOGREG_PARAMS).fit(Xs, y_pos)
            path = MODELS_DIR / f"logreg_{side}_{nested_id}.pkl"
            joblib.dump(logreg, path)
            models[f"logreg_{side}"] = logreg
            models[f"logreg_{side}_path"] = str(path)
    pred_buy, pred_sell, p_buy, p_sell = predict_meta(inner, models)
    selection = select_threshold(inner, pred_buy, pred_sell, META_TAU_CANDIDATES)
    models["selection"] = selection
    models["ppos_min"] = 0.5
    return models


def _ppos(model, Xs) -> np.ndarray:
    if model is None:
        return np.full(len(Xs), 0.5)
    proba = model.predict_proba(Xs)
    classes = list(model.classes_)
    if 1 in classes:
        return proba[:, classes.index(1)]
    return np.zeros(len(Xs))


def predict_meta(rows: list[dict], models: dict):
    Xs = models["scaler"].transform(_X(rows))
    pred_buy = models["ridge_BUY"].predict(Xs)
    pred_sell = models["ridge_SELL"].predict(Xs)
    p_buy = _ppos(models.get("logreg_BUY"), Xs)
    p_sell = _ppos(models.get("logreg_SELL"), Xs)
    return pred_buy, pred_sell, p_buy, p_sell


def apply_meta(rows: list[dict], models: dict):
    pred_buy, pred_sell, p_buy, p_sell = predict_meta(rows, models)
    extras = {
        "meta_r_BUY": pred_buy,
        "meta_r_SELL": pred_sell,
        "meta_ppos_BUY": p_buy,
        "meta_ppos_SELL": p_sell,
    }
    if not models.get("ok") or models["selection"]["fallback_wait"]:
        return baseline_a_wait(len(rows)), extras
    actions = decide_batch(pred_buy, pred_sell, models["selection"]["tau"], min_gap=0.0)
    gated = actions.copy()
    buy = actions == "BUY"
    sell = actions == "SELL"
    gated[buy & (p_buy <= 0.5)] = "WAIT"
    gated[sell & (p_sell <= 0.5)] = "WAIT"
    return gated, extras
