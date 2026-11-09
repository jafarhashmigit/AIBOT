"""Baselines, fold reports, and descriptive diagnostics. No new policy search."""

from __future__ import annotations

import numpy as np

from phase3.baselines import baseline_a_wait, baseline_b_direction, baseline_e1
from phase3.decision_policy import realized_from_action
from phase7.statistics import bootstrap_trade_r, trade_metrics


POLICY_ORDER = ("P7_PHASE6_DEFAULT", "A_WAIT", "E1_PHASE2", "B_DIRECTION", "P3_CONSERVATIVE_EV")


def decision_distribution(actions: np.ndarray) -> dict:
    n = int(len(actions))
    n_buy = int((actions == "BUY").sum())
    n_sell = int((actions == "SELL").sum())
    n_wait = int((actions == "WAIT").sum())
    return {
        "n": n,
        "BUY": n_buy,
        "SELL": n_sell,
        "WAIT": n_wait,
        "BUY_pct": n_buy / n if n else float("nan"),
        "SELL_pct": n_sell / n if n else float("nan"),
        "WAIT_pct": n_wait / n if n else float("nan"),
    }


def score_actions(eval_rows: list[dict], actions: np.ndarray) -> dict:
    dist = decision_distribution(actions)
    r, pnl, reason = realized_from_action(eval_rows, actions)
    executed = actions != "WAIT"
    n_trades = int(executed.sum())
    trade_r = r[executed]
    trade_pnl = pnl[executed]
    trade_times = [row["timestamp"] for row, take in zip(eval_rows, executed) if take]
    metrics = trade_metrics(trade_r, trade_pnl)
    boot = bootstrap_trade_r(trade_times, trade_r) if n_trades else bootstrap_trade_r([], np.array([]))
    by_fold = {}
    folds = [row["fold_id"] for row in eval_rows]
    for fold in ("WF1", "WF2", "WF3"):
        mask = np.array([f == fold for f in folds])
        if not mask.any():
            continue
        part_actions = actions[mask]
        part_rows = [row for row, keep in zip(eval_rows, mask) if keep]
        pr, ppnl, _ = realized_from_action(part_rows, part_actions)
        pexec = part_actions != "WAIT"
        by_fold[fold] = {
            **decision_distribution(part_actions),
            **trade_metrics(pr[pexec], ppnl[pexec]),
        }
    return {
        "distribution": dist,
        "pooled": {**dist, **metrics, "bootstrap": boot},
        "by_fold": by_fold,
    }


def baseline_actions(pairs: list[dict], eval_rows: list[dict]) -> dict[str, np.ndarray]:
    wide = []
    for pair, ev in zip(pairs, eval_rows):
        wide.append({
            "decision_time": pair["timestamp"],
            "pred_r_rf_BUY": pair["buy"]["pred_r_rf"],
            "pred_r_rf_SELL": pair["sell"]["pred_r_rf"],
            "actual_net_r_BUY": ev["actual_net_r_BUY"],
            "actual_net_r_SELL": ev["actual_net_r_SELL"],
            "actual_net_pnl_BUY": ev["actual_net_pnl_BUY"],
            "actual_net_pnl_SELL": ev["actual_net_pnl_SELL"],
            "actual_exit_reason_BUY": ev["actual_exit_reason_BUY"],
            "actual_exit_reason_SELL": ev["actual_exit_reason_SELL"],
        })
    n = len(wide)
    return {
        "A_WAIT": baseline_a_wait(n),
        "E1_PHASE2": baseline_e1(wide),
        "B_DIRECTION": baseline_b_direction(wide),
        "P3_CONSERVATIVE_EV": baseline_a_wait(n),
    }


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def prediction_diagnostics(pairs: list[dict], eval_rows: list[dict]) -> dict:
    """Descriptive only. Does not recalibrate or change predictions."""
    out = {}
    for side in ("BUY", "SELL"):
        p_tp = np.array([p[side.lower()]["p_tp_rf"] for p in pairs], dtype=float)
        p_sl = np.array([p[side.lower()]["p_sl_rf"] for p in pairs], dtype=float)
        pred_r = np.array([p[side.lower()]["pred_r_rf"] for p in pairs], dtype=float)
        actual_r = np.array([e[f"actual_net_r_{side}"] for e in eval_rows], dtype=float)
        out[side] = {
            "p_tp_mean": float(p_tp.mean()),
            "p_tp_std": float(p_tp.std()),
            "p_sl_mean": float(p_sl.mean()),
            "pred_r_mean": float(pred_r.mean()),
            "pred_r_std": float(pred_r.std()),
            "actual_r_mean": float(actual_r.mean()),
            "corr_pred_r_actual_r": _corr(pred_r, actual_r),
            "corr_p_tp_actual_r": _corr(p_tp, actual_r),
        }
    return out


def error_analysis(eval_rows: list[dict], final: np.ndarray, raw: np.ndarray) -> dict:
    """Descriptive. Does not propose a new rule."""
    buy_r = np.array([e["actual_net_r_BUY"] for e in eval_rows], dtype=float)
    sell_r = np.array([e["actual_net_r_SELL"] for e in eval_rows], dtype=float)
    false_buy = int(((final == "BUY") & (buy_r <= 0)).sum())
    false_sell = int(((final == "SELL") & (sell_r <= 0)).sum())
    wait = final == "WAIT"
    return {
        "final_false_BUY": false_buy,
        "final_false_SELL": false_sell,
        "WAIT_then_BUY_hypothetical_positive": int((wait & (buy_r > 0)).sum()),
        "WAIT_then_BUY_hypothetical_negative": int((wait & (buy_r <= 0)).sum()),
        "WAIT_then_SELL_hypothetical_positive": int((wait & (sell_r > 0)).sum()),
        "WAIT_then_SELL_hypothetical_negative": int((wait & (sell_r <= 0)).sum()),
        "raw_BUY": int((raw == "BUY").sum()),
        "raw_SELL": int((raw == "SELL").sum()),
        "raw_WAIT": int((raw == "WAIT").sum()),
        "raw_false_BUY": int(((raw == "BUY") & (buy_r <= 0)).sum()),
        "raw_false_SELL": int(((raw == "SELL") & (sell_r <= 0)).sum()),
        "note": (
            "Hypothetical WAIT outcomes are the unused side-outcome labels. "
            "They are not a signal to reverse WAIT. Raw counts are pre-gate."
        ),
    }
