"""Frozen predicted-volatility artifact (Phase 27 method; historical fit only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge

from phase26.data import load_h1_bars, load_m5_bars
from phase26.features import compute_orthogonal_features
from phase26.outcomes import target_vector
from phase27.vol_model import assign_regime, tertile_cuts
from phase28.constants import (
    FROZEN_VOL_FEATURES,
    FROZEN_VOL_PATH,
    FROZEN_VOL_RIDGE_ALPHA,
    FROZEN_VOL_SEED,
    FROZEN_VOL_TRAIN_CUTOFF,
    REGIME_METHOD_FROZEN,
    sha256_file,
    sha256_text,
)


def _feature_row(feats: dict[str, np.ndarray], i: int) -> np.ndarray | None:
    vec = []
    for name in FROZEN_VOL_FEATURES:
        v = float(feats[name][i])
        if not np.isfinite(v):
            return None
        vec.append(v)
    return np.asarray(vec, dtype=float)


def build_frozen_vol_artifact(*, path: Path | None = None) -> dict[str, Any]:
    """Fit once on approved historical bars <= WF3 train cutoff. Never uses forward data."""
    out_path = path or FROZEN_VOL_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from phase26.outcomes import build_rich_outcomes

    m5 = load_m5_bars()
    h1 = load_h1_bars()
    feats = compute_orthogonal_features(m5, h1)
    outcomes = build_rich_outcomes(feats, len(m5["times"]))
    y = target_vector(outcomes, "fwd_vol_12", len(m5["times"]))

    X_list, y_list = [], []
    for i, t in enumerate(m5["times"]):
        if t > FROZEN_VOL_TRAIN_CUTOFF:
            break
        if not np.isfinite(y[i]):
            continue
        vec = _feature_row(feats, i)
        if vec is None:
            continue
        X_list.append(vec)
        y_list.append(float(y[i]))
    if len(y_list) < 200:
        raise RuntimeError(f"insufficient historical samples for frozen vol model: n={len(y_list)}")

    X = np.asarray(X_list)
    yy = np.asarray(y_list)
    model = Ridge(alpha=FROZEN_VOL_RIDGE_ALPHA, random_state=FROZEN_VOL_SEED).fit(X, yy)
    pred_train = model.predict(X)
    lo, hi = tertile_cuts(pred_train)
    artifact = {
        "artifact_id": "phase28_frozen_vol_model_v1",
        "method": REGIME_METHOD_FROZEN,
        "policy": "high_only",
        "high_regime_label": "high",
        "train_cutoff_utc": FROZEN_VOL_TRAIN_CUTOFF,
        "ridge_alpha": FROZEN_VOL_RIDGE_ALPHA,
        "seed": FROZEN_VOL_SEED,
        "feature_names": list(FROZEN_VOL_FEATURES),
        "n_train": int(len(yy)),
        "coef": [float(c) for c in model.coef_],
        "intercept": float(model.intercept_),
        "tertile_cuts_predicted_train": {"p33": lo, "p67": hi},
        "train_pred_mae": float(np.mean(np.abs(pred_train - yy))),
        "note": (
            "Fitted only on approved historical data <= WF3 train cutoff. "
            "Uses Phase 26 accepted orthogonal features (OHLC-computable). "
            "Must not be updated with forward shadow observations."
        ),
    }
    text = json.dumps(artifact, indent=2, sort_keys=True)
    artifact["content_sha256"] = sha256_text(text)
    # rewrite with hash
    text2 = json.dumps(artifact, indent=2, sort_keys=True)
    out_path.write_text(text2 + "\n", encoding="utf-8")
    artifact["path"] = str(out_path)
    artifact["file_sha256"] = sha256_file(out_path)
    return artifact


def load_frozen_vol_artifact(path: Path | None = None) -> dict[str, Any]:
    p = path or FROZEN_VOL_PATH
    if not p.exists():
        raise FileNotFoundError(f"frozen vol artifact missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def verify_frozen_vol_artifact(artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    art = artifact or load_frozen_vol_artifact()
    checks = {
        "has_coef": isinstance(art.get("coef"), list) and len(art["coef"]) == len(FROZEN_VOL_FEATURES),
        "feature_names_match": tuple(art.get("feature_names") or []) == FROZEN_VOL_FEATURES,
        "train_cutoff_is_wf3": art.get("train_cutoff_utc") == FROZEN_VOL_TRAIN_CUTOFF,
        "has_tertiles": "p33" in (art.get("tertile_cuts_predicted_train") or {}),
        "method": art.get("method") == REGIME_METHOD_FROZEN,
        "policy_high_only": art.get("policy") == "high_only",
    }
    checks["all_ok"] = all(checks.values())
    return {"checks": checks, "artifact_id": art.get("artifact_id"), "n_train": art.get("n_train")}


def predict_vol_and_regime(feature_vec: np.ndarray, artifact: dict[str, Any]) -> dict[str, Any]:
    coef = np.asarray(artifact["coef"], dtype=float)
    intercept = float(artifact["intercept"])
    if feature_vec.shape[0] != coef.shape[0]:
        raise ValueError("feature vector length mismatch vs frozen coef")
    pred = float(intercept + np.dot(coef, feature_vec))
    cuts = artifact["tertile_cuts_predicted_train"]
    regime = assign_regime(pred, float(cuts["p33"]), float(cuts["p67"]))
    return {"pred_fwd_vol_12": pred, "pred_vol_regime": regime}


def feature_vector_at_index(feats: dict[str, np.ndarray], i: int) -> np.ndarray | None:
    return _feature_row(feats, i)
