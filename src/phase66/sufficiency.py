"""Evidence sufficiency gates — engineering vs statistical readiness."""

from __future__ import annotations

from typing import Any

from phase66.constants import canonical_json_sha256


def propose_sufficiency_gates(
    *,
    live_genuine_n: int,
    new_independent_date_blocks: int,
    fixture_ok: bool,
) -> dict[str, Any]:
    """
    Justified thresholds proposal based on Phase65 failure mode (date-block dependence)
    and preregistered research needs — not arbitrary tick-count targets.
    """
    # Phase 65 used date-block Bonferroni; independent sample = date blocks, not ticks.
    proposed = {
        "min_independent_open_session_date_blocks_for_discovery_proposal": 20,
        "min_independent_date_blocks_for_validation": 10,
        "min_spread_observations_per_session_state": 50,
        "max_missingness_pct_for_eligible_day": 20.0,
        "outcome_horizon_bars_m5": 12,  # research design dependent
        "regime_coverage_required": ["low_vol", "mid_vol", "high_vol"],
        "cost_uncertainty_blocks_execution_claims": True,
        "rationale": (
            "Phase 65 showed 11 unconsumed archive days insufficient under Bonferroni date-block "
            "controls. Independent N must be date/event blocks under a new preregistered protocol — "
            "not tick counts. Spread coverage informs cost stress, not edge discovery alone."
        ),
    }
    research_ready = (
        new_independent_date_blocks >= proposed["min_independent_open_session_date_blocks_for_discovery_proposal"]
        and live_genuine_n > 0
    )
    out = {
        "proposed_thresholds": proposed,
        "engineering_ready_separable": True,
        "fixture_collection_ok": fixture_ok,
        "live_genuine_observations": live_genuine_n,
        "new_independent_date_blocks": new_independent_date_blocks,
        "independent_research_evidence_sufficient": research_ready,
        "auto_start_strategy_experiments": False,
        "requires_new_preregistered_protocol": True,
        "status_flags": {
            "COLLECTION_ENGINEERING_READY": fixture_ok,
            "INSUFFICIENT_INDEPENDENT_EVIDENCE": not research_ready,
            "DATA_QUALITY_BLOCKED": False,
            "COLLECTION_OPERATIONALLY_BLOCKED": False,
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
