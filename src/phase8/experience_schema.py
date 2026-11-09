"""Experience record: decision-time fields vs outcome fields, kept separate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from phase6.information_boundary import InformationBoundaryError, is_forbidden_key, parse_stamp
from phase8.constants import HORIZON_MINUTES, RESEARCH_CUTOFF, TIME_FORMAT


DECISION_TIME_FIELD_NAMES = (
    "experience_id",
    "timestamp",
    "fold_id",
    "action",
    "raw_decision",
    "final_decision",
    "model_id",
    "expected_buy_r",
    "expected_sell_r",
    "p_tp_buy",
    "p_sl_buy",
    "p_time_buy",
    "p_tp_sell",
    "p_sl_sell",
    "p_time_sell",
    "uncertainty_buy",
    "uncertainty_sell",
    "estimated_cost",
)

OUTCOME_FIELD_NAMES = (
    "outcome_end",
    "selected_exit_reason",
    "selected_realized_r",
    "selected_realized_pnl",
    "hypothetical_buy_net_r",
    "hypothetical_sell_net_r",
    "hypothetical_buy_exit_reason",
    "hypothetical_sell_exit_reason",
    "eligible",
)


def outcome_end_for(decision_time: str) -> str:
    end = parse_stamp(decision_time)
    from datetime import timedelta
    return (end + timedelta(minutes=HORIZON_MINUTES)).strftime(TIME_FORMAT)


def assert_no_outcome_keys(payload: dict) -> None:
    for key in payload:
        if is_forbidden_key(str(key)) or str(key) in OUTCOME_FIELD_NAMES:
            raise InformationBoundaryError(f"outcome key in decision-time payload: {key}")


@dataclass(frozen=True, slots=True)
class DecisionTimeFields:
    experience_id: str
    timestamp: str
    fold_id: str
    action: str
    raw_decision: str
    final_decision: str
    model_id: str
    expected_buy_r: float
    expected_sell_r: float
    p_tp_buy: float
    p_sl_buy: float
    p_time_buy: float
    p_tp_sell: float
    p_sl_sell: float
    p_time_sell: float
    uncertainty_buy: float
    uncertainty_sell: float
    estimated_cost: float

    def __post_init__(self) -> None:
        assert_no_outcome_keys(asdict(self))
        if self.timestamp > RESEARCH_CUTOFF:
            raise InformationBoundaryError("decision timestamp after cutoff")

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OutcomeFields:
    outcome_end: str
    selected_exit_reason: str
    selected_realized_r: float | None
    selected_realized_pnl: float | None
    hypothetical_buy_net_r: float
    hypothetical_sell_net_r: float
    hypothetical_buy_exit_reason: str
    hypothetical_sell_exit_reason: str
    eligible: bool = True

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    decision_time_fields: DecisionTimeFields
    outcome_fields: OutcomeFields

    @property
    def timestamp(self) -> str:
        return self.decision_time_fields.timestamp

    @property
    def outcome_end(self) -> str:
        return self.outcome_fields.outcome_end

    def visible_at(self, decision_time: str) -> bool:
        return self.outcome_end < decision_time

    def to_mapping(self) -> dict[str, Any]:
        return {
            "decision_time_fields": self.decision_time_fields.to_mapping(),
            "outcome_fields": self.outcome_fields.to_mapping(),
        }


@dataclass(frozen=True, slots=True)
class ExperienceSummary:
    """Descriptive only. Not a trading rule."""

    n: int
    n_buy: int
    n_sell: int
    n_wait: int
    mean_selected_r: float | None
    median_selected_r: float | None
    n_win: int
    n_loss: int
    latest_outcome_end: str | None
    as_of: str
    note: str = "DESCRIPTIVE — NOT USED FOR OPTIMIZATION"

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)
