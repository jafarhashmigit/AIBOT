"""Freeze exact Phase50 learner configuration — no modifications."""

from __future__ import annotations

from typing import Any

import phase50.constants as P50
from phase50.policies import policy_registry
from phase51.constants import REPORTS_DIR, canonical_json_sha256
from phase51.progress import write_json


def freeze_phase50_learner() -> dict[str, Any]:
    """Capture immutable fingerprint of Phase50 learner/policy/context contract."""
    frozen = {
        "source_phase": 50,
        "recipe_ref": P50.RECIPE_ID,
        "learner_version": P50.LEARNER_VERSION,
        "policy_version": P50.POLICY_VERSION,
        "market_state_version": P50.MARKET_STATE_VERSION,
        "experience_schema_version": P50.EXPERIENCE_SCHEMA_VERSION,
        "spread_atr_edges": list(P50.SPREAD_ATR_EDGES),
        "min_experience_per_action": P50.MIN_EXPERIENCE_PER_ACTION,
        "shrinkage_k": P50.SHRINKAGE_K,
        "ev_margin_over_wait": P50.EV_MARGIN_OVER_WAIT,
        "uncertainty_penalty": P50.UNCERTAINTY_PENALTY,
        "bootstrap_seed": P50.BOOTSTRAP_SEED,
        "policy_registry": policy_registry(),
        "implementation_modules": [
            "phase50.learner.ShrinkageLearner",
            "phase50.context.build_context",
            "phase50.policies.decide",
            "phase50.replay.run_policy_chronological",
            "phase50.controls.make_randomizer",
        ],
        "no_modification_allowed": True,
        "note": "Phase51 imports Phase50 modules as-is. Any edit invalidates confirmation.",
    }
    frozen["frozen_learner_sha256"] = canonical_json_sha256(
        {k: v for k, v in frozen.items() if k != "frozen_learner_sha256"}
    )
    write_json(REPORTS_DIR / "frozen_learner.json", frozen)
    return frozen
