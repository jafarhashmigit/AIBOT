"""Compatibility layer: Phase 2 OOS rows → paired decision-time records.

Does not create new predictive values. Strips realized outcomes from the
decision-time view.
"""

from __future__ import annotations

from phase3.nplib import read_csv_dicts
from phase6.information_boundary import InformationBoundaryError, is_forbidden_key
from phase7.constants import (
    DECISION_TIME_PRED_FIELDS,
    OOS_PATH,
    OUTCOME_FIELDS,
)
from phase7.validation import audit_rows


def load_oos(path=OOS_PATH) -> list[dict]:
    return read_csv_dicts(path)


def _side_snapshot(row: dict) -> dict:
    out = {}
    for name in DECISION_TIME_PRED_FIELDS:
        if name not in row:
            continue
        value = row[name]
        if name.startswith("p_") or name.startswith("pred_r_"):
            out[name] = float(value)
        else:
            out[name] = value
    return out


def _strip_outcomes(payload: dict) -> dict:
    for key in list(payload):
        if key in OUTCOME_FIELDS or is_forbidden_key(key):
            raise InformationBoundaryError(f"outcome field leaked into decision-time view: {key}")
    return payload


def pair_timestamps(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (decision_time_pairs, evaluation_pairs). Evaluation holds outcomes only."""
    grouped: dict[tuple[str, str], dict[str, dict]] = {}
    for row in rows:
        key = (row["decision_time"], row["fold_id"])
        grouped.setdefault(key, {})[row["side"]] = row
    decision_pairs = []
    eval_pairs = []
    incomplete = 0
    for (stamp, fold) in sorted(grouped):
        g = grouped[(stamp, fold)]
        if "BUY" not in g or "SELL" not in g:
            incomplete += 1
            continue
        buy, sell = g["BUY"], g["SELL"]
        train_end = min(buy["training_period_end"], sell["training_period_end"])
        if train_end >= stamp:
            raise InformationBoundaryError(f"training_period_end {train_end} not before {stamp}")
        decision = _strip_outcomes({
            "timestamp": stamp,
            "fold_id": fold,
            "training_period_end": train_end,
            "feature_version": buy["feature_version"],
            "prediction_generated_at_utc": buy["prediction_generated_at_utc"],
            "buy": _side_snapshot(buy),
            "sell": _side_snapshot(sell),
        })
        evaluation = {
            "timestamp": stamp,
            "fold_id": fold,
            "actual_exit_reason_BUY": buy["actual_exit_reason"],
            "actual_net_r_BUY": float(buy["actual_net_r"]),
            "actual_net_pnl_BUY": float(buy["actual_net_pnl"]),
            "actual_exit_reason_SELL": sell["actual_exit_reason"],
            "actual_net_r_SELL": float(sell["actual_net_r"]),
            "actual_net_pnl_SELL": float(sell["actual_net_pnl"]),
        }
        decision_pairs.append(decision)
        eval_pairs.append(evaluation)
    if incomplete:
        raise InformationBoundaryError(f"incomplete BUY/SELL pairs: {incomplete}")
    return decision_pairs, eval_pairs


def load_paired() -> tuple[list[dict], list[dict], dict]:
    rows = load_oos()
    integrity = audit_rows(rows)
    decision_pairs, eval_pairs = pair_timestamps(rows)
    integrity["n_timestamps"] = len(decision_pairs)
    return decision_pairs, eval_pairs, integrity
