"""Dual research observers: H13C_BASELINE and H13C_HIGH_VOL_RESEARCH."""

from __future__ import annotations

from typing import Any

from phase16a.predictor import predict_h13c_experimental
from phase28.constants import (
    HIGH_ONLY_REGIME,
    H13C_STATUS,
    OBSERVER_BASELINE,
    OBSERVER_HIGH_VOL,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    SOURCE_SHADOW,
)


def _ensure_production_wait(pred: dict[str, Any]) -> None:
    if pred.get("final_action") != PRODUCTION_FINAL_ACTION:
        raise RuntimeError("HARD FAILURE: production final_action must remain WAIT")
    if pred.get("champion_status") != "NO_MODEL":
        raise RuntimeError("HARD FAILURE: champion must remain NO_MODEL")


def run_h13c_prediction(
    *,
    m5_closes: list[float],
    h1_rows: list[dict],
    decision_time_utc: str,
) -> dict[str, Any]:
    pred = predict_h13c_experimental(
        m5_closes=m5_closes,
        h1_rows=h1_rows,
        decision_time_utc=decision_time_utc,
    )
    _ensure_production_wait(pred)
    return pred


def build_baseline_record(
    *,
    bar: dict[str, Any],
    pred: dict[str, Any],
    gap_status: str,
    campaign_id: str,
    session_id: str,
) -> dict[str, Any]:
    open_ts = bar["bar_open_timestamp_utc"]
    close_ts = bar["bar_close_timestamp_utc"]
    action = str(pred["experimental_action"]).upper()
    dec_id = f"p28_{OBSERVER_BASELINE}_{open_ts.replace(' ', 'T')}"
    return {
        "idempotency_key": dec_id,
        "decision_id": dec_id,
        "observer_id": OBSERVER_BASELINE,
        "recipe_id": RECIPE_ID,
        "experience_source": SOURCE_SHADOW,
        "campaign_id": campaign_id,
        "session_id": session_id,
        "signal_bar_open_utc": open_ts,
        "decision_timestamp_utc": close_ts,
        "h13c_status": H13C_STATUS,
        "h13c_experimental_action": action,
        "h13c_reason": pred.get("experimental_reason"),
        "experimental_action": action,
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
        "note": "Frozen Phase 14 H13_C baseline observer; production remains WAIT.",
    }


def apply_high_only_policy(
    *,
    h13c_action: str,
    pred_vol_regime: str | None,
    vol_ok: bool,
    vol_reason: str | None = None,
) -> dict[str, Any]:
    """Phase 27 high-only: accept H13_C BUY/SELL only when predicted regime == high."""
    action = str(h13c_action).upper()
    if not vol_ok:
        return {
            "accepted": False,
            "experimental_action": "WAIT",
            "reason_code": f"vol_unavailable:{vol_reason or 'unknown'}",
            "policy_decision": "BLOCKED_VOL_UNAVAILABLE",
        }
    if action not in {"BUY", "SELL"}:
        return {
            "accepted": False,
            "experimental_action": "WAIT",
            "reason_code": "h13c_wait",
            "policy_decision": "SKIP_H13C_WAIT",
        }
    if pred_vol_regime == HIGH_ONLY_REGIME:
        return {
            "accepted": True,
            "experimental_action": action,
            "reason_code": "high_only_accept",
            "policy_decision": "ACCEPT_HIGH_ONLY",
        }
    return {
        "accepted": False,
        "experimental_action": "WAIT",
        "reason_code": f"high_only_skip_regime_{pred_vol_regime}",
        "policy_decision": "SKIP_NON_HIGH",
    }


def build_high_vol_record(
    *,
    bar: dict[str, Any],
    pred: dict[str, Any],
    vol: dict[str, Any],
    gap_status: str,
    campaign_id: str,
    session_id: str,
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
    dec_id = f"p28_{OBSERVER_HIGH_VOL}_{open_ts.replace(' ', 'T')}"
    return {
        "idempotency_key": dec_id,
        "decision_id": dec_id,
        "observer_id": OBSERVER_HIGH_VOL,
        "recipe_id": RECIPE_ID,
        "experience_source": SOURCE_SHADOW,
        "campaign_id": campaign_id,
        "session_id": session_id,
        "signal_bar_open_utc": open_ts,
        "decision_timestamp_utc": close_ts,
        "h13c_status": H13C_STATUS,
        "h13c_experimental_action": h13c_action,
        "h13c_reason": pred.get("experimental_reason"),
        "experimental_action": policy["experimental_action"],
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
        "note": (
            "Phase 27 high-only research observer using frozen predicted-vol artifact; "
            "production remains WAIT."
        ),
    }
