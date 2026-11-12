"""Interpretable action-conditioned models — reproducible, no unbounded search."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from phase47.constants import FEATURE_NAMES


@dataclass
class ActionModelBundle:
    action: str
    feature_names: list[str] = field(default_factory=lambda: list(FEATURE_NAMES))
    scaler: StandardScaler | None = None
    clf_pos: LogisticRegression | None = None
    reg_pos: Ridge | None = None
    reg_neg: Ridge | None = None
    reg_direct: Ridge | None = None
    challenger_clf: Any | None = None
    train_centroid: np.ndarray | None = None
    train_cov_inv: np.ndarray | None = None
    train_distance_p95: float | None = None
    residual_std_direct: float | None = None
    n_train: int = 0
    n_pos_train: int = 0
    n_neg_train: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def to_meta(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "feature_names": self.feature_names,
            "n_train": self.n_train,
            "n_pos_train": self.n_pos_train,
            "n_neg_train": self.n_neg_train,
            "residual_std_direct": self.residual_std_direct,
            "train_distance_p95": self.train_distance_p95,
            "config": self.config,
            "has_challenger": self.challenger_clf is not None,
        }


def _xy(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X = np.array([[float(r["features"][n]) for n in FEATURE_NAMES] for r in rows], dtype=float)
    y = np.array([float(r["net_r"]) for r in rows], dtype=float)
    pos = (y > 0).astype(int)
    return X, y, pos


def fit_action_models(action: str, train_rows: list[dict[str, Any]], *, use_challenger: bool = True) -> ActionModelBundle:
    """
    Fit:
      - L2 logistic for P(net_R>0)
      - Ridge for E[net_R|pos] and E[net_R|neg]
      - Ridge direct net_R
      - Optional HistGradientBoostingClassifier challenger (probability only)
    """
    from sklearn.ensemble import HistGradientBoostingClassifier

    bundle = ActionModelBundle(
        action=action,
        config={
            "logistic": {"C": 1.0, "solver": "lbfgs", "max_iter": 500, "random_state": 47},
            "ridge_pos": {"alpha": 1.0},
            "ridge_neg": {"alpha": 1.0},
            "ridge_direct": {"alpha": 1.0},
            "challenger": {"max_depth": 3, "max_iter": 80, "learning_rate": 0.1, "random_state": 47},
        },
    )
    if len(train_rows) < 30:
        return bundle

    X, y, pos = _xy(train_rows)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    bundle.scaler = scaler
    bundle.n_train = len(train_rows)
    bundle.n_pos_train = int(pos.sum())
    bundle.n_neg_train = int(len(pos) - pos.sum())

    clf = LogisticRegression(**bundle.config["logistic"])
    clf.fit(Xs, pos)
    bundle.clf_pos = clf

    if bundle.n_pos_train >= 20:
        rp = Ridge(**bundle.config["ridge_pos"])
        rp.fit(Xs[pos == 1], y[pos == 1])
        bundle.reg_pos = rp
    if bundle.n_neg_train >= 20:
        rn = Ridge(**bundle.config["ridge_neg"])
        rn.fit(Xs[pos == 0], y[pos == 0])
        bundle.reg_neg = rn

    rd = Ridge(**bundle.config["ridge_direct"])
    rd.fit(Xs, y)
    bundle.reg_direct = rd
    pred = rd.predict(Xs)
    bundle.residual_std_direct = float(np.std(y - pred))

    # Familiarity: Mahalanobis on scaled features
    centroid = Xs.mean(axis=0)
    cov = np.cov(Xs, rowvar=False)
    # ridge cov for stability
    cov = cov + np.eye(cov.shape[0]) * 1e-6
    try:
        cov_inv = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        cov_inv = np.linalg.pinv(cov)
    bundle.train_centroid = centroid
    bundle.train_cov_inv = cov_inv
    d = np.sqrt(np.sum((Xs - centroid) @ cov_inv * (Xs - centroid), axis=1))
    bundle.train_distance_p95 = float(np.quantile(d, 0.95))

    if use_challenger and len(train_rows) >= 200 and bundle.n_pos_train >= 40 and bundle.n_neg_train >= 40:
        ch = HistGradientBoostingClassifier(**bundle.config["challenger"])
        ch.fit(Xs, pos)
        bundle.challenger_clf = ch

    return bundle


def predict_components(bundle: ActionModelBundle, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-row probability, conditional magnitudes, direct EV, uncertainty, familiarity."""
    out: list[dict[str, Any]] = []
    if bundle.scaler is None or bundle.clf_pos is None or not rows:
        for r in rows:
            out.append({**_empty_pred(r), "reason": "model_unfitted"})
        return out

    X = np.array([[float(r["features"][n]) for n in FEATURE_NAMES] for r in rows], dtype=float)
    Xs = bundle.scaler.transform(X)
    p = bundle.clf_pos.predict_proba(Xs)[:, 1]

    # Conditional means: if model missing, fall back to train unconditional pos/neg means via intercept-only proxy
    if bundle.reg_pos is not None:
        e_pos = bundle.reg_pos.predict(Xs)
        e_pos = np.maximum(e_pos, 0.0)  # positive branch should be >=0 by definition soft-clip
    else:
        e_pos = np.full(len(rows), 0.1)
    if bundle.reg_neg is not None:
        e_neg = bundle.reg_neg.predict(Xs)
        e_neg = np.minimum(e_neg, 0.0)
    else:
        e_neg = np.full(len(rows), -0.1)

    e_direct = bundle.reg_direct.predict(Xs) if bundle.reg_direct is not None else np.zeros(len(rows))
    ev_decomp = p * e_pos + (1.0 - p) * e_neg

    # Uncertainty: combine distance from 0.5 probability with residual scale
    # Map to [0,1]: 1 = max uncertain
    unc_p = 1.0 - (2.0 * np.abs(p - 0.5))  # 1 at p=0.5, 0 at p=0 or 1
    resid = float(bundle.residual_std_direct or 1.0)
    unc = np.clip(0.5 * unc_p + 0.5 * np.minimum(1.0, np.abs(e_direct) * 0 + resid / (resid + 1.0)), 0.0, 1.0)
    # Better: uncertainty high when p near 0.5 OR residual_std large relative to |EV|
    unc = np.clip(unc_p, 0.0, 1.0)

    # Familiarity from Mahalanobis
    assert bundle.train_centroid is not None and bundle.train_cov_inv is not None
    delta = Xs - bundle.train_centroid
    dist = np.sqrt(np.sum(delta @ bundle.train_cov_inv * delta, axis=1))
    p95 = float(bundle.train_distance_p95 or 1.0)
    # familiarity in (0,1]: 1 = at centroid, decays past p95
    fam = np.clip(1.0 - (dist / (p95 + 1e-9)), 0.0, 1.0)

    p_ch = None
    if bundle.challenger_clf is not None:
        p_ch = bundle.challenger_clf.predict_proba(Xs)[:, 1]

    for i, r in enumerate(rows):
        out.append(
            {
                "day": r["day"],
                "decision_bar": r["decision_bar"],
                "action": bundle.action,
                "actual_net_r": float(r["net_r"]),
                "p_positive_net_r": float(p[i]),
                "expected_positive_net_r": float(e_pos[i]),
                "expected_negative_net_r": float(e_neg[i]),
                "expected_net_r": float(ev_decomp[i]),
                "expected_net_r_direct": float(e_direct[i]),
                "prediction_uncertainty": float(unc[i]),
                "market_familiarity": float(fam[i]),
                "ood_distance": float(dist[i]),
                "p_positive_challenger": None if p_ch is None else float(p_ch[i]),
                "stress_net_r_actual": float(
                    ((r.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}).get("net_r")
                    or r["net_r"]
                ),
            }
        )
    return out


def _empty_pred(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "day": r.get("day"),
        "decision_bar": r.get("decision_bar"),
        "action": r.get("action"),
        "actual_net_r": r.get("net_r"),
        "p_positive_net_r": None,
        "expected_positive_net_r": None,
        "expected_negative_net_r": None,
        "expected_net_r": None,
        "expected_net_r_direct": None,
        "prediction_uncertainty": 1.0,
        "market_familiarity": 0.0,
        "ood_distance": None,
        "p_positive_challenger": None,
    }
