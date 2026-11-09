"""Agent paper decision / trade / outcome. Separate from historical hypotheticals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from phase10.constants import SOURCE_PAPER, SYMBOL, TIMEFRAME
from phase10.validation import (
    SourceSeparationError,
    assert_no_outcome_keys,
    assert_timestamp_allowed,
    require_source,
)


@dataclass(frozen=True, slots=True)
class PaperDecision:
    decision_id: str
    source_type: str
    decision_timestamp: str
    market_symbol: str
    timeframe: str
    model_id: str
    expected_buy_r: float | None
    expected_sell_r: float | None
    uncertainty_buy: float
    uncertainty_sell: float
    raw_proposed_action: str
    risk_gate_result: str
    final_action: str
    decision_status: str
    provenance: str

    def __post_init__(self) -> None:
        require_source(self.source_type, SOURCE_PAPER)
        if self.raw_proposed_action not in {"BUY", "SELL", "WAIT"}:
            raise ValueError(f"invalid raw_proposed_action {self.raw_proposed_action}")
        if self.final_action not in {"BUY", "SELL", "WAIT"}:
            raise ValueError(f"invalid final_action {self.final_action}")
        if self.risk_gate_result not in {"ALLOW", "BLOCK"}:
            raise ValueError(f"invalid risk_gate_result {self.risk_gate_result}")
        if self.market_symbol != SYMBOL or self.timeframe != TIMEFRAME:
            raise ValueError("paper decision must stay on approved XAUUSD M5")
        if not str(self.decision_id).startswith("paper:"):
            raise ValueError("paper decision_id must use paper: prefix")
        assert_timestamp_allowed(self.decision_timestamp, what="paper decision_timestamp")
        assert_no_outcome_keys(asdict(self))

    @property
    def is_executable(self) -> bool:
        return (
            self.final_action in {"BUY", "SELL"}
            and self.risk_gate_result == "ALLOW"
            and self.raw_proposed_action == self.final_action
        )

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EntryReference:
    """Caller-supplied approved entry. Simulator does not invent prices."""

    timestamp: str
    price: float
    stop_loss: float | None
    take_profit: float | None
    provenance: str

    def __post_init__(self) -> None:
        assert_timestamp_allowed(self.timestamp, what="entry reference timestamp")
        if self.price <= 0:
            raise ValueError("entry price must be positive")


@dataclass(frozen=True, slots=True)
class PaperTrade:
    paper_trade_id: str
    source_type: str
    originating_decision_id: str
    side: str
    simulated_entry_timestamp: str
    simulated_entry_price: float
    simulated_stop_loss: float | None
    simulated_take_profit: float | None
    execution_status: str
    provenance: str

    def __post_init__(self) -> None:
        require_source(self.source_type, SOURCE_PAPER)
        if self.side not in {"BUY", "SELL"}:
            raise SourceSeparationError("paper trade side must be BUY or SELL")
        if self.execution_status != "open_simulated":
            raise ValueError("new paper trade execution_status must be open_simulated")
        assert_timestamp_allowed(self.simulated_entry_timestamp, what="paper entry timestamp")
        if str(self.paper_trade_id).startswith("hist:"):
            raise SourceSeparationError("paper trade cannot use historical identifier")

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PaperOutcome:
    paper_trade_id: str
    source_type: str
    simulated_exit_timestamp: str
    simulated_exit_price: float
    simulated_exit_reason: str
    simulated_realized_r: float
    simulated_net_pnl: float
    outcome_status: str
    provenance: str

    def __post_init__(self) -> None:
        require_source(self.source_type, SOURCE_PAPER)
        if self.outcome_status != "completed":
            raise ValueError("stored paper outcome must be completed")
        assert_timestamp_allowed(self.simulated_exit_timestamp, what="paper exit timestamp")

    @property
    def outcome_end(self) -> str:
        return self.simulated_exit_timestamp

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)
