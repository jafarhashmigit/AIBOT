"""Build experiences from Phase 7 journals + approved OOS outcomes. No new labels."""

from __future__ import annotations

import json

from phase6.information_boundary import parse_stamp
from phase8.constants import HORIZON_MINUTES, RESEARCH_CUTOFF, TIME_FORMAT
from phase8.experience_schema import (
    DecisionTimeFields,
    ExperienceRecord,
    OutcomeFields,
    outcome_end_for,
)


def _parse_prediction(cell: str) -> dict:
    if not cell:
        return {}
    if isinstance(cell, dict):
        return cell
    return json.loads(cell)


def _parse_uncertainty(cell: str) -> dict:
    if not cell:
        return {"buy": 0.0, "sell": 0.0}
    if isinstance(cell, dict):
        return cell
    return json.loads(cell)


def decision_time_from_phase7(row: dict) -> DecisionTimeFields:
    pred = _parse_prediction(row.get("prediction") or "{}")
    buy = pred.get("buy") or {}
    sell = pred.get("sell") or {}
    unc = _parse_uncertainty(row.get("uncertainty") or "{}")
    stamp = row["timestamp"]
    return DecisionTimeFields(
        experience_id=row.get("decision_id") or f"{stamp}_XAUUSD_M5",
        timestamp=stamp,
        fold_id=str(row.get("fold_id") or ""),
        action=str(row.get("final_decision") or "WAIT"),
        raw_decision=str(row.get("raw_decision") or ""),
        final_decision=str(row.get("final_decision") or "WAIT"),
        model_id=str(row.get("model_id") or "phase2_rf_oos"),
        expected_buy_r=float(pred.get("expected_buy_r", 0.0) or 0.0),
        expected_sell_r=float(pred.get("expected_sell_r", 0.0) or 0.0),
        p_tp_buy=float(buy.get("tp", 0.0) or 0.0),
        p_sl_buy=float(buy.get("sl", 0.0) or 0.0),
        p_time_buy=float(buy.get("time", 0.0) or 0.0),
        p_tp_sell=float(sell.get("tp", 0.0) or 0.0),
        p_sl_sell=float(sell.get("sl", 0.0) or 0.0),
        p_time_sell=float(sell.get("time", 0.0) or 0.0),
        uncertainty_buy=float(unc.get("buy", 0.0) or 0.0),
        uncertainty_sell=float(unc.get("sell", 0.0) or 0.0),
        estimated_cost=float(row.get("estimated_cost") or 0.25),
    )


def selected_outcome(action: str, eval_row: dict) -> tuple[str, float | None, float | None]:
    if action == "BUY":
        return (
            str(eval_row.get("actual_exit_reason_BUY") or eval_row.get("exit_reason") or ""),
            float(eval_row["actual_net_r_BUY"]),
            float(eval_row["actual_net_pnl_BUY"]),
        )
    if action == "SELL":
        return (
            str(eval_row.get("actual_exit_reason_SELL") or eval_row.get("exit_reason") or ""),
            float(eval_row["actual_net_r_SELL"]),
            float(eval_row["actual_net_pnl_SELL"]),
        )
    return ("", None, None)


def complete_experience(decision: DecisionTimeFields, eval_row: dict) -> tuple[ExperienceRecord | None, str | None]:
    """Attach approved outcomes after the horizon. Does not invent labels."""
    end = outcome_end_for(decision.timestamp)
    if end > RESEARCH_CUTOFF:
        return None, "outcome_end_after_cutoff"
    if "actual_net_r_BUY" not in eval_row or "actual_net_r_SELL" not in eval_row:
        return None, "missing_approved_side_outcomes"
    reason, r_sel, pnl_sel = selected_outcome(decision.final_decision, eval_row)
    outcome = OutcomeFields(
        outcome_end=end,
        selected_exit_reason=reason,
        selected_realized_r=r_sel,
        selected_realized_pnl=pnl_sel,
        hypothetical_buy_net_r=float(eval_row["actual_net_r_BUY"]),
        hypothetical_sell_net_r=float(eval_row["actual_net_r_SELL"]),
        hypothetical_buy_exit_reason=str(eval_row.get("actual_exit_reason_BUY") or ""),
        hypothetical_sell_exit_reason=str(eval_row.get("actual_exit_reason_SELL") or ""),
        eligible=True,
    )
    return ExperienceRecord(decision_time_fields=decision, outcome_fields=outcome), None


def minutes_between(a: str, b: str) -> float:
    return (parse_stamp(b) - parse_stamp(a)).total_seconds() / 60.0
