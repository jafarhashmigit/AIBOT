"""Offline paper simulator interface. No broker. No live market. No invented outcomes."""

from __future__ import annotations

from phase10.constants import SOURCE_PAPER
from phase10.paper_schema import EntryReference, PaperDecision, PaperOutcome, PaperTrade
from phase10.paper_store import PaperExperienceStore
from phase10.validation import TemporalSafetyError, paper_trade_id

BROKER_ORDER_CALLS = 0
LIVE_MARKET_CONNECTIONS = 0

FORBIDDEN_BROKER_NAMES = (
    "order_send",
    "order_close",
    "MetaTrader5",
    "place_order",
    "send_order",
    "initialize(",
    "symbol_info_tick",
)


class PaperSimulatorError(ValueError):
    pass


class PaperSimulator:
    """Deterministic offline interface. Caller must supply entry and outcome fixtures."""

    def __init__(self, store: PaperExperienceStore) -> None:
        self.store = store

    def open_trade(self, decision: PaperDecision, entry: EntryReference | None) -> PaperTrade:
        if decision.raw_proposed_action == "WAIT" or decision.final_action == "WAIT":
            raise PaperSimulatorError("WAIT cannot create a paper trade")
        if decision.risk_gate_result == "BLOCK":
            raise PaperSimulatorError("BLOCKED action cannot create a paper trade")
        if not decision.is_executable:
            raise PaperSimulatorError("decision is not executable as a paper trade")
        if entry is None:
            raise PaperSimulatorError("valid approved entry reference is required")
        if entry.timestamp != decision.decision_timestamp:
            raise PaperSimulatorError("entry reference timestamp must match the decision")
        trade = PaperTrade(
            paper_trade_id=paper_trade_id(decision.decision_id),
            source_type=SOURCE_PAPER,
            originating_decision_id=decision.decision_id,
            side=decision.final_action,
            simulated_entry_timestamp=entry.timestamp,
            simulated_entry_price=entry.price,
            simulated_stop_loss=entry.stop_loss,
            simulated_take_profit=entry.take_profit,
            execution_status="open_simulated",
            provenance=entry.provenance,
        )
        self.store.record_trade(trade)
        return trade

    def complete_trade(
        self,
        trade: PaperTrade,
        *,
        as_of: str,
        exit_timestamp: str,
        exit_price: float,
        exit_reason: str,
        realized_r: float,
        net_pnl: float,
        provenance: str,
    ) -> PaperOutcome:
        """Attach a caller-supplied fixture outcome. Does not invent market results."""
        if exit_price <= 0:
            raise PaperSimulatorError("exit price must be provided by the fixture")
        outcome = PaperOutcome(
            paper_trade_id=trade.paper_trade_id,
            source_type=SOURCE_PAPER,
            simulated_exit_timestamp=exit_timestamp,
            simulated_exit_price=exit_price,
            simulated_exit_reason=exit_reason,
            simulated_realized_r=float(realized_r),
            simulated_net_pnl=float(net_pnl),
            outcome_status="completed",
            provenance=provenance,
        )
        if not (outcome.outcome_end < as_of):
            raise TemporalSafetyError("paper outcome attaches only after completion")
        self.store.attach_outcome(outcome, as_of=as_of)
        return outcome


def broker_order_calls() -> int:
    return BROKER_ORDER_CALLS


def live_market_connections() -> int:
    return LIVE_MARKET_CONNECTIONS


def assert_no_broker_surface() -> None:
    import inspect
    src = inspect.getsource(PaperSimulator)
    lowered = src.lower()
    for name in FORBIDDEN_BROKER_NAMES:
        if name.lower() in lowered:
            raise PaperSimulatorError(f"broker surface referenced: {name}")
