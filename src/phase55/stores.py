"""Isolated Phase55 engineering-test experience stores — never production Phase54 roots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase50.experience_store import ExperienceStore, new_experience
from phase54.constants import FEATURE_VERSION, HORIZON_BARS
from phase55.constants import (
    ENGINEERING_TAG,
    TEST_HIST_DIR,
    TEST_SHADOW_DIR,
)


def test_historical_store() -> ExperienceStore:
    return ExperienceStore("HISTORICAL_HYPOTHETICAL", root=TEST_HIST_DIR)


def test_shadow_store() -> ExperienceStore:
    return ExperienceStore("AGENT_SHADOW", root=TEST_SHADOW_DIR)


def production_counts() -> dict[str, Any]:
    from phase54.experience import historical_store, shadow_store

    h = historical_store()
    s = shadow_store()
    return {
        "hist_n": h.n,
        "shadow_n": s.n,
        "hist_path": str(h.path),
        "shadow_path": str(s.path),
    }


def record_test_shadow(
    *,
    store: ExperienceStore,
    decision: dict[str, Any],
    market_state: dict[str, Any],
    net_r: float,
    outcome_timestamp_utc: str,
) -> dict[str, Any]:
    rec = new_experience(
        source="AGENT_SHADOW",
        decision_timestamp_utc=str(decision.get("timestamp_utc")),
        market_state_id=str(decision.get("market_state_id") or market_state.get("market_state_id")),
        action=str(decision.get("action")),
        decision_context={
            "decision_id": decision.get("decision_id"),
            "reason_codes": decision.get("reason_codes"),
            ENGINEERING_TAG: True,
            "namespace": "phase55_engineering_test",
        },
        actual_costed_outcome_net_r=float(net_r),
        outcome_horizon_bars=HORIZON_BARS,
        outcome_timestamp_utc=outcome_timestamp_utc,
        regime_context=market_state.get("regime") or {},
        policy_version=str(decision.get("model_policy_version")),
        expected_value=None,
        decision_reason=",".join(decision.get("reason_codes") or []),
        confidence=None,
    )
    rec["feature_representation_version"] = FEATURE_VERSION
    rec[ENGINEERING_TAG] = True
    store.append(rec)
    return rec


def assert_not_production_path(path: Path) -> None:
    p = str(path).replace("\\", "/").lower()
    if "/phase54/" in p and "/phase55/" not in p:
        raise RuntimeError(f"refusing write to production path: {path}")
