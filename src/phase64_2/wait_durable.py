"""Durable idempotent WAIT experience — deterministic ID; no hist/shadow merge."""

from __future__ import annotations

from typing import Any

from phase50.experience_store import ExperienceStore, new_experience
from phase54.constants import FEATURE_VERSION, HORIZON_BARS, POLICY_VERSION
from phase64_2.constants import wait_experience_id
from phase64_2.intent_state import CrashInjected, finalize_wait_intent
from phase64_2.hardened_journal import HardenedIntentJournal


def record_wait_experience_durable(
    *,
    shadow: ExperienceStore,
    journal: HardenedIntentJournal,
    decision: dict[str, Any],
    market_state: dict[str, Any],
    intent_id: str,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """
    Append WAIT AGENT_SHADOW experience once per canonical decision_id.
    Then finalize intent → WAIT_FINALIZED.
    """
    decision_id = str(decision["decision_id"])
    exp_id = wait_experience_id(decision_id)
    existing_ids = {r.get("experience_id") for r in shadow.all()}
    created = False
    if exp_id not in existing_ids:
        if crash_at == "during_wait_experience_append":
            # Simulate crash before durable append completes
            raise CrashInjected("during_wait_experience_append")
        rec = new_experience(
            source="AGENT_SHADOW",
            decision_timestamp_utc=str(decision.get("timestamp_utc")),
            market_state_id=str(decision.get("market_state_id") or market_state.get("market_state_id")),
            action="WAIT",
            decision_context={
                "decision_id": decision_id,
                "runtime_uuid_decision_id": decision.get("runtime_uuid_decision_id"),
                "intent_id": intent_id,
                "snapshot_id": decision.get("snapshot_id"),
                "reason_codes": decision.get("reason_codes"),
                "data_quality_status": decision.get("data_quality_status"),
                "wait_durable": True,
                "phase64_2": True,
            },
            actual_costed_outcome_net_r=0.0,
            outcome_horizon_bars=HORIZON_BARS,
            outcome_timestamp_utc=str(
                market_state.get("bar_timestamp_utc") or decision.get("timestamp_utc")
            ),
            regime_context=market_state.get("regime") or {},
            policy_version=str(decision.get("model_policy_version") or POLICY_VERSION),
            expected_value=decision.get("expected_net_r"),
            decision_reason=",".join(decision.get("reason_codes") or []) or "WAIT",
            confidence=decision.get("confidence"),
        )
        rec["experience_id"] = exp_id  # override random UUID with deterministic
        rec["feature_representation_version"] = FEATURE_VERSION
        shadow.append(rec)
        shadow.flush()
        created = True
    else:
        rec = next(r for r in shadow.all() if r.get("experience_id") == exp_id)

    fin = finalize_wait_intent(
        journal,
        decision_id=decision_id,
        intent_id=intent_id,
        experience_id=exp_id,
        crash_at=crash_at,
    )
    return {
        "experience_id": exp_id,
        "created": created,
        "intent_status": fin.get("intent_status"),
        "record": rec,
        "source": "AGENT_SHADOW",
        "historical_untouched": True,
    }
