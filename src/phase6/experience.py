"""Experience = decision-time snapshots + later realized outcome."""

from __future__ import annotations

from dataclasses import dataclass

from phase6.decision_engine import DecisionResult
from phase6.outcome import Outcome, assert_horizon_complete
from phase6.schemas import Observation, Prediction, Uncertainty


@dataclass(frozen=True, slots=True)
class Experience:
    observation_snapshot: dict
    prediction_snapshot: dict
    decision_snapshot: dict
    realized_outcome: dict
    evaluation_timestamp: str

    def to_mapping(self) -> dict:
        return {
            "observation_snapshot": self.observation_snapshot,
            "prediction_snapshot": self.prediction_snapshot,
            "decision_snapshot": self.decision_snapshot,
            "realized_outcome": self.realized_outcome,
            "evaluation_timestamp": self.evaluation_timestamp,
        }


def make_experience(
    observation: Observation,
    prediction: Prediction,
    decision: DecisionResult,
    outcome: Outcome,
    *,
    evaluation_timestamp: str,
) -> Experience:
    assert_horizon_complete(
        decision_timestamp=observation.timestamp,
        evaluation_timestamp=evaluation_timestamp,
    )
    return Experience(
        observation_snapshot=observation.to_mapping(),
        prediction_snapshot={
            "expected_buy_r": prediction.expected_buy_r,
            "expected_sell_r": prediction.expected_sell_r,
            "model_id": prediction.model_id,
        },
        decision_snapshot=decision.to_mapping(),
        realized_outcome=outcome.to_mapping(),
        evaluation_timestamp=evaluation_timestamp,
    )
