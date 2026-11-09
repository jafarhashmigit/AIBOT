"""Paper decision journal and completed paper-trade store. Rejects historical records."""

from __future__ import annotations

from phase10.constants import RESEARCH_CUTOFF, SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.paper_schema import PaperDecision, PaperOutcome, PaperTrade
from phase10.validation import (
    SourceSeparationError,
    TemporalSafetyError,
    is_visible,
    require_source,
)


class PaperExperienceStore:
    def __init__(self) -> None:
        self._decisions: dict[str, PaperDecision] = {}
        self._trades: dict[str, PaperTrade] = {}
        self._outcomes: dict[str, PaperOutcome] = {}
        self._last_decision_ts: str | None = None
        self._trade_by_decision: dict[str, str] = {}

    def record_decision(self, decision: PaperDecision) -> None:
        if not isinstance(decision, PaperDecision):
            raise SourceSeparationError("PaperExperienceStore.record_decision accepts PaperDecision only")
        require_source(decision.source_type, SOURCE_PAPER)
        if decision.decision_id.startswith("hist:"):
            raise SourceSeparationError("cross-source identifier collision")
        if decision.decision_id in self._decisions:
            raise SourceSeparationError(f"duplicate paper decision_id {decision.decision_id}")
        if self._last_decision_ts is not None and decision.decision_timestamp < self._last_decision_ts:
            raise TemporalSafetyError("paper decision append is not chronological; backdating rejected")
        self._decisions[decision.decision_id] = decision
        self._last_decision_ts = decision.decision_timestamp

    def record_trade(self, trade: PaperTrade) -> None:
        if not isinstance(trade, PaperTrade):
            raise SourceSeparationError("PaperExperienceStore.record_trade accepts PaperTrade only")
        require_source(trade.source_type, SOURCE_PAPER)
        if getattr(trade, "source_type", None) == SOURCE_HISTORICAL:
            raise SourceSeparationError("cannot write HISTORICAL_HYPOTHETICAL into PaperExperienceStore")
        decision = self._decisions.get(trade.originating_decision_id)
        if decision is None:
            raise SourceSeparationError("paper trade requires an existing paper decision")
        if not decision.is_executable:
            raise SourceSeparationError("WAIT or BLOCKED decisions cannot create a paper trade")
        if trade.side != decision.final_action:
            raise SourceSeparationError("paper trade side must match final_action")
        if trade.paper_trade_id in self._trades:
            raise SourceSeparationError(f"duplicate paper_trade_id {trade.paper_trade_id}")
        if trade.originating_decision_id in self._trade_by_decision:
            raise SourceSeparationError("decision already has a paper trade")
        self._trades[trade.paper_trade_id] = trade
        self._trade_by_decision[trade.originating_decision_id] = trade.paper_trade_id

    def attach_outcome(self, outcome: PaperOutcome, *, as_of: str) -> None:
        if not isinstance(outcome, PaperOutcome):
            raise SourceSeparationError("attach_outcome accepts PaperOutcome only")
        require_source(outcome.source_type, SOURCE_PAPER)
        if outcome.paper_trade_id not in self._trades:
            raise TemporalSafetyError("cannot attach outcome without a paper trade")
        if outcome.paper_trade_id in self._outcomes:
            raise TemporalSafetyError("paper outcome already attached")
        if not is_visible(outcome.outcome_end, as_of):
            raise TemporalSafetyError("paper outcome attaches only after completion (outcome_end < as_of)")
        trade = self._trades[outcome.paper_trade_id]
        if outcome.outcome_end <= trade.simulated_entry_timestamp:
            raise TemporalSafetyError("paper exit must be after entry")
        self._outcomes[outcome.paper_trade_id] = outcome

    def reject_historical(self, record) -> None:
        raise SourceSeparationError("cannot write historical hypothetical into PaperExperienceStore")

    def query_completed(self, as_of: str) -> list[dict]:
        if as_of > RESEARCH_CUTOFF:
            raise TemporalSafetyError("query as_of after cutoff")
        out = []
        for trade_id, outcome in sorted(self._outcomes.items(), key=lambda kv: kv[1].outcome_end):
            if is_visible(outcome.outcome_end, as_of):
                trade = self._trades[trade_id]
                decision = self._decisions[trade.originating_decision_id]
                out.append({
                    "source_type": SOURCE_PAPER,
                    "decision": decision.to_mapping(),
                    "trade": trade.to_mapping(),
                    "outcome": outcome.to_mapping(),
                })
        return out

    def decision_count(self) -> int:
        return len(self._decisions)

    def trade_count(self) -> int:
        return len(self._trades)

    def completed_count(self, as_of: str) -> int:
        return len(self.query_completed(as_of))
