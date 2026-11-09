"""Read-only schema compatibility. Does not merge or normalize records."""

from __future__ import annotations

from phase10.constants import SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.historical_schema import HistoricalDecisionFields, HistoricalOutcomeFields
from phase10.historical_store import HistoricalExperienceStore
from phase10.paper_schema import PaperDecision, PaperOutcome, PaperTrade
from phase10.paper_store import PaperExperienceStore


def _fields(cls) -> list[str]:
    return list(cls.__dataclass_fields__.keys())


def audit_compatibility(
    historical: HistoricalExperienceStore,
    paper: PaperExperienceStore,
) -> dict:
    hist_decision = set(_fields(HistoricalDecisionFields))
    hist_outcome = set(_fields(HistoricalOutcomeFields))
    paper_decision = set(_fields(PaperDecision))
    paper_trade = set(_fields(PaperTrade))
    paper_outcome = set(_fields(PaperOutcome))

    differences = [
        {
            "concept": "identity",
            "historical": "experience_id prefixed hist:",
            "paper": "decision_id prefixed paper:; paper_trade_id only if a trade exists",
            "equivalent": False,
        },
        {
            "concept": "side_or_action",
            "historical": "side in {BUY, SELL} only; both sides exist per timestamp",
            "paper": "raw_proposed_action and final_action in {BUY, SELL, WAIT}",
            "equivalent": False,
        },
        {
            "concept": "realized_net_r",
            "historical": "outcome.actual_net_r (hypothetical path)",
            "paper": "outcome.simulated_realized_r (only after a completed paper trade)",
            "equivalent": False,
        },
        {
            "concept": "outcome_status",
            "historical": "completed records only in store",
            "paper": "decisions may exist with no trade and no outcome",
            "equivalent": False,
        },
        {
            "concept": "provenance",
            "historical": "phase2_oos_predictions.csv",
            "paper": "phase9_replay_log.csv for decisions; fixture provenance for any future simulated fill",
            "equivalent": False,
        },
        {
            "concept": "costs",
            "historical": "embedded in approved Phase 2 actual_net_r / actual_net_pnl",
            "paper": "PaperDecision has no cost field; future adapter must carry approved cost convention",
            "equivalent": False,
        },
        {
            "concept": "timestamps",
            "historical": "decision_timestamp and outcome_end as naive UTC-corrected strings",
            "paper": "decision_timestamp; simulated_exit_timestamp is outcome_end for trades",
            "equivalent": True,
            "note": "same TIME_FORMAT; not the same event",
        },
        {
            "concept": "missing_values",
            "historical": "hypothetical_entry_reference may be null; not fabricated",
            "paper": "completed metrics are null when no outcomes exist; never replaced with zero performance",
            "equivalent": False,
        },
    ]

    adapter_required = [
        "Keep source_type on every converted row; never drop it.",
        "Map historical.side → contract.side; map paper.final_action → contract.side and skip WAIT unless explicitly eligible as a non-trade sample.",
        "Map historical.actual_net_r → contract.realized_net_r with outcome_provenance=historical_oos.",
        "Map paper.simulated_realized_r → contract.realized_net_r with outcome_provenance=agent_paper_simulator.",
        "Do not treat a historical BUY hypothetical as an agent BUY paper trade.",
        "Filter by source_type before any pooled fit.",
        "Carry as-of availability: eligible iff outcome_end < decision_time of the target step.",
    ]

    overlap = hist_decision & paper_decision
    return {
        "passed": True,
        "merged_records": False,
        "normalized_in_place": False,
        "combined_learning_implemented": False,
        "historical_decision_fields": sorted(hist_decision),
        "historical_outcome_fields": sorted(hist_outcome),
        "paper_decision_fields": sorted(paper_decision),
        "paper_trade_fields": sorted(paper_trade),
        "paper_outcome_fields": sorted(paper_outcome),
        "shared_field_names": sorted(overlap),
        "historical_n": len(historical),
        "paper_decisions": paper.decision_count(),
        "paper_trades": paper.trade_count(),
        "differences": differences,
        "shared_learner_compatible_without_adapter": False,
        "explicit_adapter_required": True,
        "adapter_rules": adapter_required,
        "note": "A HISTORICAL_HYPOTHETICAL path is not an AGENT_PAPER trade.",
        "sources": [SOURCE_HISTORICAL, SOURCE_PAPER],
    }
