"""Reproducible signal identity."""

from __future__ import annotations

import hashlib
import json

from phase6.constants import (
    COST_ASSUMPTION_VERSION,
    DECISION_ENGINE_VERSION,
    FEATURE_VERSION_REF,
    JOURNAL_SCHEMA_VERSION,
    OBSERVATION_VERSION,
    RISK_GATE_VERSION,
)
from phase6.schemas import Observation, SignalVersions


def canonical_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def observation_hash(observation: Observation) -> str:
    return canonical_hash(observation.to_mapping())


def make_signal_id(
    *,
    timestamp: str,
    model_id: str,
    feature_version: str,
    decision_engine_version: str,
    risk_gate_version: str,
    cost_assumption_version: str,
    observation_hash_hex: str,
) -> str:
    return canonical_hash({
        "timestamp": timestamp,
        "model_id": model_id,
        "feature_version": feature_version,
        "decision_engine_version": decision_engine_version,
        "risk_gate_version": risk_gate_version,
        "cost_assumption_version": cost_assumption_version,
        "observation_hash": observation_hash_hex,
    })


def versions_for(
    observation: Observation,
    *,
    model_id: str,
    decision_engine_version: str = DECISION_ENGINE_VERSION,
    risk_gate_version: str = RISK_GATE_VERSION,
    cost_assumption_version: str = COST_ASSUMPTION_VERSION,
) -> SignalVersions:
    obs_hash = observation.data_hash or observation_hash(observation)
    sid = make_signal_id(
        timestamp=observation.timestamp,
        model_id=model_id,
        feature_version=observation.feature_version or FEATURE_VERSION_REF,
        decision_engine_version=decision_engine_version,
        risk_gate_version=risk_gate_version,
        cost_assumption_version=cost_assumption_version,
        observation_hash_hex=obs_hash,
    )
    return SignalVersions(
        signal_id=sid,
        model_id=model_id,
        feature_version=observation.feature_version or FEATURE_VERSION_REF,
        decision_engine_version=decision_engine_version,
        risk_gate_version=risk_gate_version,
        cost_assumption_version=cost_assumption_version,
        observation_version=observation.observation_version or OBSERVATION_VERSION,
        journal_schema_version=JOURNAL_SCHEMA_VERSION,
    )
