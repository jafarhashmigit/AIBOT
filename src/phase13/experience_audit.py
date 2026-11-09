"""Part F: experience-source handling. No combined learner. No fabricated paper trades."""

from __future__ import annotations


def experience_source_audit() -> dict:
    return {
        "historical_hypothetical": {
            "source_type": "HISTORICAL_HYPOTHETICAL",
            "used_in_phase13": True,
            "usage": "Existing m5_side_outcomes net_r/net_pnl as hypothetical path outcomes for rule scoring",
            "schema_mixed_with_paper": False,
        },
        "agent_paper": {
            "source_type": "AGENT_PAPER",
            "used_in_phase13": False,
            "completed_paper_trades": 0,
            "fabricated": False,
            "note": "Phase 11 reported zero completed paper outcomes; Phase 13 does not invent any",
        },
        "combined_learner": {
            "implemented": False,
            "justification_required": True,
            "reason_not_combined": (
                "Phase 11 compatibility audit required a separately justified adapter. "
                "No such experiment is in scope for Phase 13 discovery, and paper n=0 "
                "provides no supervised paper target."
            ),
        },
        "temporal_safety": {
            "holdout_opened": False,
            "post_cutoff_decisions_scored": False,
            "max_decision_time": "2026-09-29 17:50:00",
        },
    }
