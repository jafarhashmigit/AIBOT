"""First AIBOT candidate interface — frozen Phase50 learner, paper decisions only."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from phase50.constants import LEARNER_VERSION, MARKET_STATE_VERSION, POLICY_VERSION
from phase50.context import build_context
from phase50.learner import ShrinkageLearner
from phase50.policies import decide, estimates_from_separated

UTC = timezone.utc


class FrozenAIBOTCandidate:
    """
    decide(market_state, experience_snapshot) -> decision object
    Does NOT retrain during inference; caller supplies causal experience snapshot.
    """

    def __init__(self, frozen_learner_sha256: str):
        self.frozen_learner_sha256 = frozen_learner_sha256
        self.learner = ShrinkageLearner()
        self.learner_version = LEARNER_VERSION
        self.policy_version = POLICY_VERSION
        self.market_state_version = MARKET_STATE_VERSION

    def decide(self, market_state: dict[str, Any], experience_snapshot: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        """
        market_state: {features: {...}, timestamp_utc: str, ...}
        experience_snapshot: {HISTORICAL_HYPOTHETICAL: [...], AGENT_SHADOW: [...]} already causal-filtered
        """
        features = market_state.get("features") or {}
        ctx = build_context(features)
        est, meta = estimates_from_separated(self.learner, experience_snapshot, "historical")
        q = self.learner.q_values(est, ctx)
        decision = decide(policy_id="POLICY_1", q=q, experience_count=int(meta.get("n_used") or 0))
        action = decision["action"]
        q_block = (decision.get("q") or {}).get(action) if action != "WAIT" else {"q": 0.0, "se": 0.0}
        if not isinstance(q_block, dict):
            q_block = {"q": 0.0, "se": 0.0}
        return {
            "timestamp_utc": market_state.get("timestamp_utc"),
            "market_state_version": self.market_state_version,
            "learner_version": self.learner_version,
            "policy_version": self.policy_version,
            "frozen_learner_sha256": self.frozen_learner_sha256,
            "action": action,
            "estimated_ev": q_block.get("q_penalized", q_block.get("q", 0.0)),
            "uncertainty": q_block.get("se"),
            "reason": decision.get("reason"),
            "experience_count": decision.get("experience_count"),
            "decision_id": uuid.uuid4().hex,
            "q_detail": decision.get("q"),
            "creation_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "paper_only": True,
            "no_orders": True,
        }
