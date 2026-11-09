"""Deterministic decision baselines. Thresholds, if any, use inner data only."""

from __future__ import annotations

import numpy as np

from phase3.constants import C_TAU_CANDIDATES, D_TAU_CANDIDATES, DEFAULT_MIN_GAP
from phase3.decision_policy import decide_batch, select_threshold
from phase3.nplib import col


def baseline_a_wait(n: int) -> np.ndarray:
    return np.full(n, "WAIT", dtype=object)


def baseline_b_direction(rows: list[dict]) -> np.ndarray:
    buy = col(rows, "pred_r_rf_BUY")
    sell = col(rows, "pred_r_rf_SELL")
    return decide_batch(buy, sell, tau=float("-inf"), min_gap=DEFAULT_MIN_GAP)


def baseline_e1(rows: list[dict]) -> np.ndarray:
    buy = col(rows, "pred_r_rf_BUY")
    sell = col(rows, "pred_r_rf_SELL")
    out = np.full(len(rows), "WAIT", dtype=object)
    out[(buy >= sell) & (buy > 0)] = "BUY"
    out[(sell > buy) & (sell > 0)] = "SELL"
    return out


def fit_c_threshold(inner: list[dict]) -> dict:
    return select_threshold(inner, col(inner, "pred_r_rf_BUY"), col(inner, "pred_r_rf_SELL"),
                            C_TAU_CANDIDATES, min_gap=DEFAULT_MIN_GAP)


def apply_c(rows: list[dict], fit: dict) -> np.ndarray:
    if fit["fallback_wait"]:
        return baseline_a_wait(len(rows))
    return decide_batch(col(rows, "pred_r_rf_BUY"), col(rows, "pred_r_rf_SELL"),
                        fit["tau"], DEFAULT_MIN_GAP)


def fit_d_threshold(inner: list[dict]) -> dict:
    return select_threshold(inner, col(inner, "p_tp_minus_sl_rf_BUY"),
                            col(inner, "p_tp_minus_sl_rf_SELL"),
                            D_TAU_CANDIDATES, min_gap=DEFAULT_MIN_GAP)


def apply_d(rows: list[dict], fit: dict) -> np.ndarray:
    if fit["fallback_wait"]:
        return baseline_a_wait(len(rows))
    return decide_batch(col(rows, "p_tp_minus_sl_rf_BUY"), col(rows, "p_tp_minus_sl_rf_SELL"),
                        fit["tau"], DEFAULT_MIN_GAP)
