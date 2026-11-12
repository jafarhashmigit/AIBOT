"""Two separate experience systems — wraps phase50 schemas; isolated phase54 roots."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from phase50.availability import assert_no_leakage, experience_available_at
from phase50.experience_store import ExperienceStore, dual_query, new_experience
from phase50.schemas import validate_experience
from phase54.constants import (
    FEATURE_VERSION,
    HIST_EXP_DIR,
    HORIZON_BARS,
    POLICY_VERSION,
    SHADOW_EXP_DIR,
)

UTC = timezone.utc


def historical_store() -> ExperienceStore:
    return ExperienceStore("HISTORICAL_HYPOTHETICAL", root=HIST_EXP_DIR)


def shadow_store() -> ExperienceStore:
    return ExperienceStore("AGENT_SHADOW", root=SHADOW_EXP_DIR)


def record_agent_shadow(
    *,
    store: ExperienceStore,
    decision: dict[str, Any],
    market_state: dict[str, Any],
    net_r: float,
    outcome_timestamp_utc: str,
    regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rec = new_experience(
        source="AGENT_SHADOW",
        decision_timestamp_utc=str(decision.get("timestamp_utc")),
        market_state_id=str(decision.get("market_state_id") or market_state.get("market_state_id")),
        action=str(decision.get("action")),
        decision_context={
            "decision_id": decision.get("decision_id"),
            "reason_codes": decision.get("reason_codes"),
            "risk": decision.get("risk_estimate"),
            "data_quality_status": decision.get("data_quality_status"),
        },
        actual_costed_outcome_net_r=float(net_r),
        outcome_horizon_bars=HORIZON_BARS,
        outcome_timestamp_utc=outcome_timestamp_utc,
        regime_context=regime or market_state.get("regime") or {},
        policy_version=str(decision.get("model_policy_version") or POLICY_VERSION),
        expected_value=decision.get("expected_net_r"),
        decision_reason=",".join(decision.get("reason_codes") or []) or "unspecified",
        confidence=decision.get("confidence"),
    )
    rec["feature_representation_version"] = FEATURE_VERSION
    store.append(rec)
    return rec


def record_historical_hypothetical(
    *,
    store: ExperienceStore,
    day: str,
    decision_idx: int,
    bar_ts: str,
    market_state_id: str,
    action: str,
    net_r: float,
    outcome_timestamp_utc: str,
    regime: dict[str, Any],
    provenance: str,
) -> dict[str, Any]:
    assert action in ("BUY", "SELL", "WAIT")
    rec = new_experience(
        source="HISTORICAL_HYPOTHETICAL",
        decision_timestamp_utc=bar_ts,
        market_state_id=market_state_id,
        action=action,
        decision_context={
            "day": day,
            "decision_idx": decision_idx,
            "counterfactual": True,
            "provenance": provenance,
        },
        actual_costed_outcome_net_r=float(net_r),
        outcome_horizon_bars=HORIZON_BARS,
        outcome_timestamp_utc=outcome_timestamp_utc,
        regime_context=regime,
        policy_version="historical_counterfactual_v1",
        decision_reason="historical_counterfactual",
    )
    rec["feature_representation_version"] = FEATURE_VERSION
    store.append(rec)
    return rec


def stores_are_isolated(hist: ExperienceStore, shadow: ExperienceStore) -> bool:
    return hist.source != shadow.source and hist.path != shadow.path


__all__ = [
    "ExperienceStore",
    "assert_no_leakage",
    "dual_query",
    "experience_available_at",
    "historical_store",
    "record_agent_shadow",
    "record_historical_hypothetical",
    "shadow_store",
    "stores_are_isolated",
    "validate_experience",
]
