"""Realized outcome. Created only after the evaluation window has completed."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from phase6.information_boundary import InformationBoundaryError, parse_stamp
from phase6.schemas import Observation


HORIZON_BARS = 12
BAR_MINUTES = 5
HORIZON_MINUTES = HORIZON_BARS * BAR_MINUTES


@dataclass(frozen=True, slots=True)
class Outcome:
    """Future-realized trade outcome. Must not be stored on Observation."""

    entry_timestamp: str
    exit_timestamp: str
    exit_reason: str
    gross_return_usd: float
    cost_usd: float
    net_return_r: float
    duration_bars: int
    eligible: bool = True
    side: str = ""

    def to_mapping(self) -> dict:
        return asdict(self)


def assert_horizon_complete(*, decision_timestamp: str, evaluation_timestamp: str) -> None:
    start = parse_stamp(decision_timestamp)
    now = parse_stamp(evaluation_timestamp)
    elapsed_min = (now - start).total_seconds() / 60.0
    if elapsed_min < HORIZON_MINUTES:
        raise InformationBoundaryError(
            f"outcome requested at {evaluation_timestamp} before horizon "
            f"({HORIZON_BARS} bars / {HORIZON_MINUTES} minutes after {decision_timestamp})"
        )


def attach_outcome(
    observation: Observation,
    outcome: Outcome,
    *,
    evaluation_timestamp: str,
) -> dict:
    """Return an enrichment payload. Does not mutate the observation."""
    if not isinstance(observation, Observation):
        raise TypeError("observation must be an Observation")
    if not isinstance(outcome, Outcome):
        raise TypeError("outcome must be an Outcome")
    assert_horizon_complete(
        decision_timestamp=observation.timestamp,
        evaluation_timestamp=evaluation_timestamp,
    )
    return {
        "decision_timestamp": observation.timestamp,
        "evaluation_timestamp": evaluation_timestamp,
        "realized_outcome": outcome.to_mapping(),
        "realized_R": outcome.net_return_r,
        "exit_reason": outcome.exit_reason,
    }


def observation_rejects_outcome_fields() -> bool:
    """Sanity helper for tests: Outcome field names are not Observation attributes."""
    outcome_fields = set(Outcome.__dataclass_fields__)
    observation_fields = set(Observation.__dataclass_fields__)
    return outcome_fields.isdisjoint(observation_fields)
