"""Side-specific Ridge (alpha=1.0). Expanding window. No outcome features."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from phase6.information_boundary import InformationBoundaryError, is_forbidden_key
from phase9.constants import (
    MIN_EXPERIENCES_PER_SIDE,
    OUTCOME_FEATURE_NAMES,
    PHASE9_LEARNER_FEATURE_ALLOWLIST,
    RIDGE_ALPHA,
)


def features_from_pair(pair: dict) -> dict[str, float]:
    buy, sell = pair["buy"], pair["sell"]
    vals = {
        "p_tp_rf_BUY": float(buy["p_tp_rf"]),
        "p_sl_rf_BUY": float(buy["p_sl_rf"]),
        "p_time_rf_BUY": float(buy["p_time_rf"]),
        "p_tp_rf_SELL": float(sell["p_tp_rf"]),
        "p_sl_rf_SELL": float(sell["p_sl_rf"]),
        "p_time_rf_SELL": float(sell["p_time_rf"]),
        "pred_r_rf_BUY": float(buy["pred_r_rf"]),
        "pred_r_rf_SELL": float(sell["pred_r_rf"]),
        "pred_r_ridge_BUY": float(buy["pred_r_ridge"]),
        "pred_r_ridge_SELL": float(sell["pred_r_ridge"]),
    }
    vals["pred_r_rf_diff"] = vals["pred_r_rf_BUY"] - vals["pred_r_rf_SELL"]
    vals["p_tp_rf_diff"] = vals["p_tp_rf_BUY"] - vals["p_tp_rf_SELL"]
    assert_allowlist(vals)
    return vals


def assert_allowlist(vals: dict) -> None:
    extra = set(vals) - set(PHASE9_LEARNER_FEATURE_ALLOWLIST)
    if extra:
        raise InformationBoundaryError(f"features not on allowlist: {sorted(extra)}")
    for name in vals:
        if is_forbidden_key(name) or name in OUTCOME_FEATURE_NAMES:
            raise InformationBoundaryError(f"outcome field used as feature: {name}")


def vector(vals: dict) -> np.ndarray:
    return np.array([vals[name] for name in PHASE9_LEARNER_FEATURE_ALLOWLIST], dtype=float)


@dataclass
class RidgeState:
    xtx: np.ndarray
    xty: np.ndarray
    n: int
    earliest: str | None = None
    latest_outcome_end: str | None = None


class ExperienceRidge:
    """Incremental Ridge: beta = argmin ||Xw - y||^2 + alpha ||w_no_intercept||^2."""

    def __init__(self, alpha: float = RIDGE_ALPHA, min_n: int = MIN_EXPERIENCES_PER_SIDE) -> None:
        self.alpha = float(alpha)
        self.min_n = int(min_n)
        p = len(PHASE9_LEARNER_FEATURE_ALLOWLIST) + 1
        self.buy = RidgeState(np.zeros((p, p)), np.zeros(p), 0)
        self.sell = RidgeState(np.zeros((p, p)), np.zeros(p), 0)

    def observe(self, feat: dict, y_buy: float, y_sell: float, *, timestamp: str, outcome_end: str) -> None:
        assert_allowlist(feat)
        x = np.concatenate([[1.0], vector(feat)])
        outer = np.outer(x, x)
        for state, y in ((self.buy, y_buy), (self.sell, y_sell)):
            state.xtx += outer
            state.xty += x * float(y)
            state.n += 1
            if state.earliest is None:
                state.earliest = timestamp
            state.latest_outcome_end = outcome_end

    def available(self) -> bool:
        return self.buy.n >= self.min_n and self.sell.n >= self.min_n

    def _beta(self, state: RidgeState) -> np.ndarray | None:
        if state.n < self.min_n:
            return None
        a = state.xtx.copy()
        p = a.shape[0]
        penalty = np.eye(p) * self.alpha
        penalty[0, 0] = 0.0
        a = a + penalty
        try:
            return np.linalg.solve(a, state.xty)
        except np.linalg.LinAlgError:
            return np.linalg.lstsq(a, state.xty, rcond=None)[0]

    def predict(self, feat: dict) -> tuple[float | None, float | None]:
        assert_allowlist(feat)
        if not self.available():
            return None, None
        x = np.concatenate([[1.0], vector(feat)])
        b_buy, b_sell = self._beta(self.buy), self._beta(self.sell)
        if b_buy is None or b_sell is None:
            return None, None
        return float(x @ b_buy), float(x @ b_sell)

    def audit(self, *, fit_timestamp: str) -> dict:
        return {
            "fit_timestamp": fit_timestamp,
            "alpha": self.alpha,
            "min_n": self.min_n,
            "feature_columns": list(PHASE9_LEARNER_FEATURE_ALLOWLIST),
            "target_column": "hypothetical_side_net_r",
            "BUY": {
                "sample_count": self.buy.n,
                "earliest": self.buy.earliest,
                "latest_outcome_end": self.buy.latest_outcome_end,
            },
            "SELL": {
                "sample_count": self.sell.n,
                "earliest": self.sell.earliest,
                "latest_outcome_end": self.sell.latest_outcome_end,
            },
            "available": self.available(),
        }
