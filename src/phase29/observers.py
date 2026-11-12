"""Dual Phase 29 observers — reuse frozen Phase 14/27/28 decision logic."""

from __future__ import annotations

from typing import Any

from phase28.observers import apply_high_only_policy, run_h13c_prediction
from phase29.constants import (
    H13C_STATUS,
    OBSERVER_A,
    OBSERVER_B,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    SOURCE_SHADOW,
    STRATEGY_ID,
    SYMBOL,
)


def build_baseline_record(
    *,
    bar: dict[str, Any],
    pred: dict[str, Any],
    gap_status: str,
    campaign_id: str,
    session_id: str,
    levels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    open_ts = bar["bar_open_timestamp_utc"]
    close_ts = bar["bar_close_timestamp_utc"]
    action = str(pred["experimental_action"]).upper()
    dec_id = f"p29_{OBSERVER_A}_{open_ts.replace(' ', 'T')}"
    event_id = dec_id
    row = {
        "idempotency_key": dec_id,
        "decision_id": dec_id,
        "event_id": event_id,
        "observer_id": OBSERVER_A,
        "recipe_id": RECIPE_ID,
        "experience_source": SOURCE_SHADOW,
        "campaign_id": campaign_id,
        "session_id": session_id,
        "symbol": SYMBOL,
        "strategy": STRATEGY_ID,
        "signal_bar_open_utc": open_ts,
        "decision_timestamp_utc": close_ts,
        "candle_close_timestamp_utc": close_ts,
        "h13c_status": H13C_STATUS,
        "h13c_experimental_action": action,
        "h13c_reason": pred.get("experimental_reason"),
        "experimental_action": action,
        "direction": action if action in {"BUY", "SELL"} else "WAIT",
        "accepted": action in {"BUY", "SELL"},
        "reason_code": pred.get("experimental_reason") or "h13c_decision",
        "final_action": PRODUCTION_FINAL_ACTION,
        "production_action": PRODUCTION_FINAL_ACTION,
        "champion_status": "NO_MODEL",
        "frozen_cuts": pred.get("frozen_cuts"),
        "feature_snapshot": pred.get("feature_snapshot"),
        "h1_context": pred.get("h1_context"),
        "gap_status": gap_status,
        "policy": "baseline_h13c",
        "pred_fwd_vol_12": None,
        "pred_vol_regime": None,
        "entry": None,
        "tp_level": None,
        "sl_level": None,
        "atr": None,
        "note": "Phase 29 baseline H13_C observer; production remains WAIT.",
    }
    if levels and action in {"BUY", "SELL"}:
        row["entry"] = levels["entry"]
        row["tp_level"] = levels["tp_level"]
        row["sl_level"] = levels["sl_level"]
        row["atr"] = levels["atr"]
    return row


def build_high_vol_record(
    *,
    bar: dict[str, Any],
    pred: dict[str, Any],
    vol: dict[str, Any],
    gap_status: str,
    campaign_id: str,
    session_id: str,
    levels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    open_ts = bar["bar_open_timestamp_utc"]
    close_ts = bar["bar_close_timestamp_utc"]
    h13c_action = str(pred["experimental_action"]).upper()
    policy = apply_high_only_policy(
        h13c_action=h13c_action,
        pred_vol_regime=vol.get("pred_vol_regime"),
        vol_ok=bool(vol.get("ok")),
        vol_reason=vol.get("reason"),
    )
    dec_id = f"p29_{OBSERVER_B}_{open_ts.replace(' ', 'T')}"
    action = policy["experimental_action"]
    row = {
        "idempotency_key": dec_id,
        "decision_id": dec_id,
        "event_id": dec_id,
        "observer_id": OBSERVER_B,
        "recipe_id": RECIPE_ID,
        "experience_source": SOURCE_SHADOW,
        "campaign_id": campaign_id,
        "session_id": session_id,
        "symbol": SYMBOL,
        "strategy": STRATEGY_ID,
        "signal_bar_open_utc": open_ts,
        "decision_timestamp_utc": close_ts,
        "candle_close_timestamp_utc": close_ts,
        "h13c_status": H13C_STATUS,
        "h13c_experimental_action": h13c_action,
        "h13c_reason": pred.get("experimental_reason"),
        "experimental_action": action,
        "direction": action if action in {"BUY", "SELL"} else "WAIT",
        "accepted": policy["accepted"],
        "reason_code": policy["reason_code"],
        "policy_decision": policy["policy_decision"],
        "final_action": PRODUCTION_FINAL_ACTION,
        "production_action": PRODUCTION_FINAL_ACTION,
        "champion_status": "NO_MODEL",
        "frozen_cuts": pred.get("frozen_cuts"),
        "feature_snapshot": pred.get("feature_snapshot"),
        "h1_context": pred.get("h1_context"),
        "gap_status": gap_status,
        "policy": "high_only",
        "pred_fwd_vol_12": vol.get("pred_fwd_vol_12"),
        "pred_vol_regime": vol.get("pred_vol_regime"),
        "vol_ok": bool(vol.get("ok")),
        "entry": None,
        "tp_level": None,
        "sl_level": None,
        "atr": None,
        "note": "Phase 29 high-only research observer; never alters production WAIT.",
    }
    if levels and policy["accepted"]:
        row["entry"] = levels["entry"]
        row["tp_level"] = levels["tp_level"]
        row["sl_level"] = levels["sl_level"]
        row["atr"] = levels["atr"]
    return row


__all__ = [
    "run_h13c_prediction",
    "build_baseline_record",
    "build_high_vol_record",
    "apply_high_only_policy",
]
