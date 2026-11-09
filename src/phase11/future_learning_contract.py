"""Proposed contract for a future shared learner. Not an implementation."""

from __future__ import annotations

CONTRACT_ID = "phase11_future_learning_contract_v1"
STATUS = "PROPOSED — NOT IMPLEMENTED"


def future_learning_contract() -> dict:
    return {
        "contract_id": CONTRACT_ID,
        "status": STATUS,
        "learner_implemented": False,
        "records_combined": False,
        "required_fields": [
            "source_type",
            "experience_id",
            "decision_timestamp",
            "outcome_end",
            "side_or_action",
            "feature_provenance",
            "outcome_provenance",
            "cost_convention",
            "sample_eligibility",
            "as_of_available",
        ],
        "source_type_values": ["HISTORICAL_HYPOTHETICAL", "AGENT_PAPER"],
        "filter_by_source_required": True,
        "evaluations": {
            "A_historical_only": "Fit/score using HISTORICAL_HYPOTHETICAL rows only.",
            "B_paper_only": "Fit/score using AGENT_PAPER completed trades only. Unavailable while paper outcomes = 0.",
            "C_separate_before_combination": "Report A and B independently before any controlled pooled experiment.",
        },
        "eligibility": {
            "as_of_rule": "outcome_end < decision_timestamp of the learning step",
            "equal_timestamp": "unavailable",
            "incomplete": "excluded",
            "WAIT_paper": "not a trade sample unless a future phase defines a non-trade experience class",
            "BLOCKED_paper": "not an executed trade",
        },
        "adapter": {
            "required": True,
            "must_not_drop_source_type": True,
            "must_not_equate_hypothetical_with_paper_trade": True,
            "historical_realized_r": "actual_net_r",
            "paper_realized_r": "simulated_realized_r",
            "costs": "preserve Phase 2/6 approved cost convention; do not invent a new cost model",
        },
        "forbidden_in_this_phase": [
            "implementing the learner",
            "pooling unlabeled rows",
            "training ML models",
            "loosening RiskGate to create paper trades",
        ],
    }
