"""Historical decision journal. Decision-time fields are separable from outcomes."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from phase3.constants import (
    FEATURE_VERSION,
    FROZEN_POLICY_ID,
    JOURNAL_PATH,
    POLICY_VERSION,
    RECIPE_ID,
)
from phase3.decision_policy import block_reason, realized_from_action
from phase3.nplib import fmt_time, write_csv_dicts


def build_journal(outer: list[dict], actions: np.ndarray, *, nested_id: str,
                  inner_end, tau, min_gap, k, mapping_mae: dict) -> list[dict]:
    r, pnl, reason = realized_from_action(outer, actions)
    inner_end_s = fmt_time(inner_end)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tau_s = "" if tau is None else float(tau)
    rows = []
    for i, rec in enumerate(outer):
        action = str(actions[i])
        wait = action == "WAIT"
        train_end = min(rec["training_period_end_BUY"], rec["training_period_end_SELL"])
        tau_for_reason = float("-inf") if tau is None else float(tau)
        rows.append({
            "decision_time": fmt_time(rec["decision_time"]),
            "nested_fold_id": nested_id,
            "phase2_fold_id": rec["fold_id"],
            "action": action,
            "block_reason": ("inner_selection_fallback_wait" if tau is None else
                             block_reason(float(rec["cons_ev_BUY"]), float(rec["cons_ev_SELL"]),
                                          tau_for_reason, min_gap, action)),
            "ev_BUY": float(rec["ev_BUY"]),
            "ev_SELL": float(rec["ev_SELL"]),
            "cons_ev_BUY": float(rec["cons_ev_BUY"]),
            "cons_ev_SELL": float(rec["cons_ev_SELL"]),
            "pred_r_rf_BUY": float(rec["pred_r_rf_BUY"]),
            "pred_r_rf_SELL": float(rec["pred_r_rf_SELL"]),
            "p_tp_rf_BUY": float(rec["p_tp_rf_BUY"]),
            "p_sl_rf_BUY": float(rec["p_sl_rf_BUY"]),
            "p_time_rf_BUY": float(rec["p_time_rf_BUY"]),
            "p_tp_rf_SELL": float(rec["p_tp_rf_SELL"]),
            "p_sl_rf_SELL": float(rec["p_sl_rf_SELL"]),
            "p_time_rf_SELL": float(rec["p_time_rf_SELL"]),
            "uncertainty_penalty_BUY": float(mapping_mae["BUY"]),
            "uncertainty_penalty_SELL": float(mapping_mae["SELL"]),
            "tau": tau_s,
            "min_gap": float(min_gap),
            "uncertainty_k": float(k),
            "policy_id": FROZEN_POLICY_ID,
            "decision_rule_version": POLICY_VERSION,
            "primary_clf_model_id_BUY": rec["primary_clf_model_id_BUY"],
            "primary_reg_model_id_BUY": rec["primary_reg_model_id_BUY"],
            "primary_clf_model_id_SELL": rec["primary_clf_model_id_SELL"],
            "primary_reg_model_id_SELL": rec["primary_reg_model_id_SELL"],
            "decision_model_id": f"ev_map_{nested_id}",
            "training_period_end_primary": fmt_time(train_end),
            "inner_train_end": inner_end_s,
            "feature_version": FEATURE_VERSION,
            "recipe_id": RECIPE_ID,
            "journal_schema_version": "phase3-1.0",
            "prediction_generated_at_utc": generated,
            "outcome_buy_exit_reason": rec["actual_exit_reason_BUY"],
            "outcome_sell_exit_reason": rec["actual_exit_reason_SELL"],
            "outcome_buy_net_r": float(rec["actual_net_r_BUY"]),
            "outcome_sell_net_r": float(rec["actual_net_r_SELL"]),
            "outcome_buy_net_pnl": float(rec["actual_net_pnl_BUY"]),
            "outcome_sell_net_pnl": float(rec["actual_net_pnl_SELL"]),
            "outcome_selected_exit_reason": "" if wait else str(reason[i]),
            "outcome_selected_net_r": 0.0 if wait else float(r[i]),
            "outcome_selected_net_pnl": 0.0 if wait else float(pnl[i]),
            "outcome_profitable": bool((not wait) and r[i] > 0),
            "outcome_is_wait": bool(wait),
        })
    return rows


def write_journal(frames: list[list[dict]], path=JOURNAL_PATH) -> list[dict]:
    out = [row for part in frames for row in part]
    if out:
        write_csv_dicts(path, out)
    return out
