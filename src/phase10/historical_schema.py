"""Historical hypothetical experience. Not an agent paper trade."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from phase10.constants import SOURCE_HISTORICAL
from phase10.validation import (
    assert_no_outcome_keys,
    assert_timestamp_allowed,
    require_source,
)


@dataclass(frozen=True, slots=True)
class HistoricalDecisionFields:
    experience_id: str
    source_type: str
    decision_timestamp: str
    side: str
    fold_id: str
    model_id: str
    p_tp_rf: float
    p_sl_rf: float
    p_time_rf: float
    pred_r_rf: float
    pred_r_ridge: float
    provenance: str
    hypothetical_entry_reference: str | None = None

    def __post_init__(self) -> None:
        require_source(self.source_type, SOURCE_HISTORICAL)
        if self.side not in {"BUY", "SELL"}:
            raise ValueError(f"historical side must be BUY or SELL, got {self.side}")
        assert_timestamp_allowed(self.decision_timestamp, what="historical decision_timestamp")
        assert_no_outcome_keys(asdict(self))
        if not str(self.experience_id).startswith("hist:"):
            raise ValueError("historical experience_id must use hist: prefix")

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HistoricalOutcomeFields:
    outcome_end: str
    exit_reason: str
    actual_net_r: float
    realized_pnl: float | None
    outcome_status: str

    def __post_init__(self) -> None:
        if self.outcome_status != "completed":
            raise ValueError("historical outcome_status must be completed to store")
        assert_timestamp_allowed(self.outcome_end, what="historical outcome_end")

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HistoricalExperience:
    """Hypothetical BUY or SELL path. Never described as a paper execution."""

    decision: HistoricalDecisionFields
    outcome: HistoricalOutcomeFields

    def __post_init__(self) -> None:
        if self.decision.source_type != SOURCE_HISTORICAL:
            raise ValueError("historical experience source mismatch")
        if not (self.outcome.outcome_end > self.decision.decision_timestamp):
            raise ValueError("outcome_end must be after decision_timestamp")

    @property
    def experience_id(self) -> str:
        return self.decision.experience_id

    @property
    def source_type(self) -> str:
        return SOURCE_HISTORICAL

    @property
    def decision_timestamp(self) -> str:
        return self.decision.decision_timestamp

    @property
    def outcome_end(self) -> str:
        return self.outcome.outcome_end

    def to_mapping(self) -> dict[str, Any]:
        return {
            "source_type": SOURCE_HISTORICAL,
            "decision": self.decision.to_mapping(),
            "outcome": self.outcome.to_mapping(),
            "note": "HISTORICAL_HYPOTHETICAL — not an agent paper trade",
        }
