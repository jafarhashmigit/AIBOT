"""OOS classification, regression, and pre-declared economic readout."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_fscore_support,
)

from evaluation.bootstrap import day_cluster_bootstrap_mean
from evaluation.metrics import expectancy, win_rate
from research_rf_m5_model_comparison import max_drawdown, profit_factor
from phase2.constants import OUTCOME_CLASSES, SEED, SELECTION_RULE, SIDES


def _econ(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0}
    net = trades["net_pnl"]
    r = trades["net_pnl_r"]
    return {
        "trades": int(len(trades)),
        "buy_trades": int((trades["side"] == "BUY").sum()) if "side" in trades else None,
        "sell_trades": int((trades["side"] == "SELL").sum()) if "side" in trades else None,
        "win_rate": win_rate(net.to_numpy(float)),
        "net_pnl": float(net.sum()),
        "avg_r": float(r.mean()),
        "total_r": float(r.sum()),
        "profit_factor": float(profit_factor(net)),
        "max_drawdown_usd": float(max_drawdown(net)),
        "max_drawdown_r": float(max_drawdown(r)),
        "expectancy_usd": expectancy(net.to_numpy(float)),
        "expectancy_r": expectancy(r.to_numpy(float)),
        "tp": int((trades["exit_reason"] == "TP").sum()) if "exit_reason" in trades else None,
        "sl": int((trades["exit_reason"] == "SL").sum()) if "exit_reason" in trades else None,
        "time": int((trades["exit_reason"] == "TIME").sum()) if "exit_reason" in trades else None,
        "note": "P&L already includes approved spread floor and $0.05/side costs from side outcomes.",
    }


def _probs(df: pd.DataFrame, prefix: str) -> np.ndarray:
    return df[[f"p_tp_{prefix}", f"p_sl_{prefix}", f"p_time_{prefix}"]].to_numpy(dtype=float)


def _onehot(y: np.ndarray) -> np.ndarray:
    index = {c: i for i, c in enumerate(OUTCOME_CLASSES)}
    out = np.zeros((len(y), len(OUTCOME_CLASSES)))
    for i, val in enumerate(y):
        out[i, index[val]] = 1.0
    return out


def classification_report_for(df: pd.DataFrame, prefix: str) -> dict:
    y = df["actual_exit_reason"].to_numpy()
    p = _probs(df, prefix)
    pred = np.array(OUTCOME_CLASSES)[p.argmax(axis=1)]
    labels = list(OUTCOME_CLASSES)
    prec, rec, f1, sup = precision_recall_fscore_support(y, pred, labels=labels, zero_division=0)
    cm = confusion_matrix(y, pred, labels=labels)
    brier = float(np.mean(np.sum((p - _onehot(y)) ** 2, axis=1)))
    return {
        "n": int(len(df)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, labels=labels, average="macro", zero_division=0)),
        "log_loss": float(log_loss(y, p, labels=labels)),
        "brier_multiclass": brier,
        "per_class": {
            labels[i]: {"precision": float(prec[i]), "recall": float(rec[i]),
                        "f1": float(f1[i]), "support": int(sup[i])}
            for i in range(len(labels))
        },
        "confusion_matrix": {"labels": labels, "matrix": cm.tolist()},
    }


def regression_report_for(df: pd.DataFrame, col: str) -> dict:
    y = df["actual_net_r"].to_numpy(dtype=float)
    p = df[col].to_numpy(dtype=float)
    if len(y) < 2:
        corr = float("nan")
    else:
        corr = float(np.corrcoef(p, y)[0, 1])
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "mean_actual_net_r": float(y.mean()),
        "mean_predicted_net_r": float(p.mean()),
        "corr_pred_actual": corr,
        "calibration_by_quintile": _quintile_calibration(p, y),
    }


def _quintile_calibration(pred, actual) -> list[dict]:
    s = pd.Series(pred)
    try:
        bins = pd.qcut(s, 5, duplicates="drop")
    except ValueError:
        return []
    rows = []
    for name, idx in s.groupby(bins, observed=True).groups.items():
        rows.append({
            "bin": str(name),
            "n": int(len(idx)),
            "mean_predicted": float(pred[list(idx)].mean()),
            "mean_actual": float(actual[list(idx)].mean()),
        })
    return rows


def apply_e1(preds: pd.DataFrame, pred_col: str = "pred_r_rf") -> pd.DataFrame:
    """Pre-declared rule E1. One row per timestamp or none (WAIT)."""
    wide = preds.pivot(index=["decision_time", "fold_id"], columns="side", values=pred_col)
    actual_r = preds.pivot(index=["decision_time", "fold_id"], columns="side", values="actual_net_r")
    actual_pnl = preds.pivot(index=["decision_time", "fold_id"], columns="side", values="actual_net_pnl")
    exit_reason = preds.pivot(index=["decision_time", "fold_id"], columns="side", values="actual_exit_reason")
    rows = []
    for idx in wide.index:
        buy, sell = wide.loc[idx, "BUY"], wide.loc[idx, "SELL"]
        if pd.isna(buy) or pd.isna(sell):
            continue
        if buy >= sell and buy > 0:
            side = "BUY"
        elif sell > buy and sell > 0:
            side = "SELL"
        else:
            continue
        rows.append({
            "decision_time": idx[0],
            "fold_id": idx[1],
            "window": idx[1],
            "side": side,
            "signal_time": idx[0],
            "predicted_r": float(wide.loc[idx, side]),
            "net_pnl_r": float(actual_r.loc[idx, side]),
            "net_pnl": float(actual_pnl.loc[idx, side]),
            "exit_reason": exit_reason.loc[idx, side],
        })
    return pd.DataFrame(rows)


def economic_report(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"n": 0, "note": "no selected timestamps"}
    pooled = _econ(trades)
    by_fold = {str(fold): _econ(part) for fold, part in trades.groupby("fold_id", sort=True)}
    by_side = {str(side): _econ(part) for side, part in trades.groupby("side", sort=True)}
    boot = day_cluster_bootstrap_mean(trades, value_col="net_pnl_r", time_col="decision_time",
                                      n_samples=2000, seed=SEED)
    return {
        "rule": SELECTION_RULE,
        "pooled": pooled,
        "by_fold": by_fold,
        "by_side": by_side,
        "day_cluster_bootstrap_mean_r": boot,
        "finding_class": "exploratory",
        "note": "E1 is a frozen readout, not a live policy. Positive accuracy is not an edge.",
    }


def evaluate_all(preds: pd.DataFrame) -> dict:
    clf_models = {"prior": "prior", "logreg": "logreg", "rf": "rf"}
    reg_models = {"const": "pred_r_const", "ridge": "pred_r_ridge", "rf": "pred_r_rf"}
    classification, regression = {}, {}
    for name, prefix in clf_models.items():
        classification[name] = {
            "pooled": classification_report_for(preds, prefix),
            "by_side": {s: classification_report_for(preds[preds["side"] == s], prefix) for s in SIDES},
            "by_fold": {f: classification_report_for(part, prefix)
                        for f, part in preds.groupby("fold_id", sort=True)},
        }
    for name, col in reg_models.items():
        regression[name] = {
            "pooled": regression_report_for(preds, col),
            "by_side": {s: regression_report_for(preds[preds["side"] == s], col) for s in SIDES},
            "by_fold": {f: regression_report_for(part, col)
                        for f, part in preds.groupby("fold_id", sort=True)},
        }
    e1_trades = apply_e1(preds, "pred_r_rf")
    return {
        "n_oos_rows": int(len(preds)),
        "n_oos_buy": int((preds["side"] == "BUY").sum()),
        "n_oos_sell": int((preds["side"] == "SELL").sum()),
        "folds": sorted(preds["fold_id"].unique().tolist()),
        "classification": classification,
        "regression": regression,
        "economic_e1_rf_reg": economic_report(e1_trades),
        "economic_e1_n_selected": int(len(e1_trades)),
        "permutation_a_phase1": {
            "status": "not_run",
            "note": "The Phase 1 200-retrain label-block permutation remains incomplete. "
                    "This phase does not mark it passed.",
        },
    }
