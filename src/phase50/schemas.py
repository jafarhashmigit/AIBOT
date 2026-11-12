"""Immutable experience / decision schemas with versioning."""

from __future__ import annotations

from typing import Any

from phase50.constants import (
    EXPERIENCE_SCHEMA_VERSION,
    LEARNER_VERSION,
    MARKET_STATE_VERSION,
    POLICY_VERSION,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase50.progress import write_json

REQUIRED_EXPERIENCE_FIELDS = (
    "experience_id",
    "source",
    "decision_timestamp_utc",
    "market_state_id",
    "action",
    "decision_context",
    "actual_costed_outcome_net_r",
    "outcome_horizon_bars",
    "outcome_timestamp_utc",
    "regime_context",
    "feature_representation_version",
    "policy_version",
    "creation_timestamp_utc",
    "experience_schema_version",
)

REQUIRED_SHADOW_EXTRA = ("decision_reason",)


def experience_schema() -> dict[str, Any]:
    schema = {
        "experience_schema_version": EXPERIENCE_SCHEMA_VERSION,
        "sources": ["HISTORICAL_HYPOTHETICAL", "AGENT_SHADOW"],
        "actions": ["BUY", "SELL", "WAIT"],
        "required_fields": list(REQUIRED_EXPERIENCE_FIELDS),
        "agent_shadow_extra_fields": list(REQUIRED_SHADOW_EXTRA),
        "causality_rule": "outcome_timestamp_utc < decision_timestamp_utc for use at a later decision",
        "merge_forbidden": True,
        "policy_version": POLICY_VERSION,
        "learner_version": LEARNER_VERSION,
        "market_state_version": MARKET_STATE_VERSION,
    }
    schema["schema_sha256"] = canonical_json_sha256({k: v for k, v in schema.items() if k != "schema_sha256"})
    write_json(REPORTS_DIR / "experience_schema.json", schema)
    return schema


def validate_experience(rec: dict[str, Any]) -> list[str]:
    errs = []
    for f in REQUIRED_EXPERIENCE_FIELDS:
        if f not in rec:
            errs.append(f"missing:{f}")
    if rec.get("source") not in ("HISTORICAL_HYPOTHETICAL", "AGENT_SHADOW"):
        errs.append("bad_source")
    if rec.get("action") not in ("BUY", "SELL", "WAIT"):
        errs.append("bad_action")
    if rec.get("source") == "AGENT_SHADOW":
        for f in REQUIRED_SHADOW_EXTRA:
            if f not in rec:
                errs.append(f"shadow_missing:{f}")
    return errs
