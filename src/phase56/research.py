"""Research-readiness interfaces — prepare only; no training or hypotheses."""

from __future__ import annotations

from typing import Any

from phase56.constants import AGENT_VERSION, POLICY_VERSION, REPORTS_DIR, RECIPE_ID, canonical_json_sha256
from phase56.progress import write_json


def research_readiness_registry() -> dict[str, Any]:
    reg = {
        "recipe": RECIPE_ID,
        "agent_version": AGENT_VERSION,
        "no_training": True,
        "no_strategy_hypotheses": True,
        "interfaces": {
            "versioned_observations": True,
            "versioned_feature_snapshots": "phase49_features via observation.features + feature_version",
            "decision_to_outcome_traceability": "decision_id ↔ position_id ↔ experience_id",
            "regime_metadata": "observation.regime",
            "experience_provenance_separated": ["HISTORICAL_HYPOTHETICAL", "AGENT_SHADOW"],
            "non_overlapping_outcome_maturity": "HORIZON_BARS=12; monitor across candles",
            "policy_version_tracking": POLICY_VERSION,
            "future_calibrated_model_adapter": "phase54.decision.Policy protocol",
        },
        "engineering_test_isolation": "phase55 EngineeringTestPolicy must not be production default",
        "production_policy": "NullPolicy / NO_MODEL / WAIT",
    }
    reg["registry_sha256"] = canonical_json_sha256({k: v for k, v in reg.items() if k != "registry_sha256"})
    write_json(REPORTS_DIR / "research_readiness.json", reg)
    return reg
