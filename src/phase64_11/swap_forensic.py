"""Swap forensic reconciliation — preserve both observations; no forced agreement."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    LIVE_ACCOUNT,
    REQUIRES_GENUINE_ACCOUNT_EVENT,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    SWAP_MODE_POINTS,
    SWAP_ROLLOVER3DAYS,
    SWAP_SHORT_LIVE,
    UNKNOWN_FOR_EXECUTION,
    USER_REPORTED,
    canonical_json_sha256,
)


def forensic_swap_reconciliation() -> dict[str, Any]:
    rows = [
        {
            "observation": "phase63_user_reported",
            "source": "Phase63 ACTIVE_XAUUSDM_SPEC",
            "value": SWAP_LONG_PHASE63,
            "unit": "POINTS (claimed)",
            "direction": "LONG",
            "volume": "UNSPECIFIED (metadata rate)",
            "nights": "N/A (rate not charged overnight)",
            "status": "PRESERVED_USER_REPORTED",
            "evidence_type": USER_REPORTED,
        },
        {
            "observation": "phase64_7_live_symbol_info",
            "source": "LIVE_MT5 symbol_info",
            "value": SWAP_LONG_PHASE64_7,
            "unit": "POINTS (swap_mode=1)",
            "direction": "LONG",
            "volume": "UNSPECIFIED (metadata rate per lot/day)",
            "nights": "N/A (rate not charged overnight)",
            "status": "PRESERVED_LIVE_ACCOUNT",
            "evidence_type": LIVE_ACCOUNT,
        },
        {
            "observation": "live_swap_short",
            "source": "LIVE_MT5 symbol_info",
            "value": SWAP_SHORT_LIVE,
            "unit": "POINTS",
            "direction": "SHORT",
            "volume": "UNSPECIFIED",
            "nights": "N/A",
            "status": "LIVE_ACCOUNT",
            "evidence_type": LIVE_ACCOUNT,
        },
    ]

    hypotheses = [
        {"id": "different_volume", "explains_conflict": False, "note": "Both are symbol metadata rates, not volume-scaled charges"},
        {"id": "different_nights", "explains_conflict": False, "note": "Rates are per-night coefficients, not multi-night sums"},
        {"id": "long_vs_short", "explains_conflict": False, "note": "Both observations are long-side"},
        {"id": "swap_unit_mismatch", "explains_conflict": "POSSIBLE_UNPROVEN", "note": "Both labeled POINTS; unit mismatch not proven"},
        {"id": "contract_size", "explains_conflict": False, "note": "Contract size 100 verified; would affect both similarly if same unit"},
        {"id": "points_vs_currency", "explains_conflict": "POSSIBLE_UNPROVEN", "note": "Live swap_mode=1 POINTS; Phase63 claimed POINTS"},
        {
            "id": "triple_swap_day",
            "explains_conflict": False,
            "note": f"rollover3days={SWAP_ROLLOVER3DAYS} multiplies overnight charge; does not rewrite swap_long metadata",
        },
        {"id": "symbol_spec_change_over_time", "explains_conflict": "PLAUSIBLE", "note": "Broker can change swap points; no continuous history"},
        {"id": "account_specific_config", "explains_conflict": "PLAUSIBLE_UNPROVEN", "note": "Phase63 account state not API-verified then"},
        {"id": "server_time_rollover", "explains_conflict": False, "note": "Affects when charge applies, not the stored rate conflict"},
        {"id": "valuation_timing", "explains_conflict": "PLAUSIBLE", "note": "Different observation times"},
        {"id": "historical_vs_current_spec", "explains_conflict": "PLAUSIBLE", "note": "Primary working explanation"},
        {"id": "rounding", "explains_conflict": False, "note": "Delta ≈ -156.1 too large for rounding"},
        {"id": "data_source_differences", "explains_conflict": "PLAUSIBLE", "note": "UI Spec vs API"},
    ]

    reconciled = False
    conflict_status = "explainable_but_not_reconciled"
    # Policy rule without claiming single historical truth
    execution_policy = {
        "overnight_financing_rate_source": "LIVE_ACCOUNT_symbol_info_at_decision_time",
        "phase63_observation": "PRESERVED_HISTORICAL_NOT_INTERCHANGEABLE",
        "actual_charged_swap_on_position": "REQUIRES_GENUINE_OVERNIGHT_DEAL_EVIDENCE",
        "status_for_execution_model": UNKNOWN_FOR_EXECUTION,
        "note": (
            "Current live rate may be used as the *current metadata rate* for research stress, "
            "but overnight monetary outcome remains unproven without a hold/deal. "
            "Conflict is not resolved to one historical value."
        ),
    }

    classification = REQUIRES_GENUINE_ACCOUNT_EVENT
    reasoning = (
        "The metadata conflict is explainable (spec/time/source change) but not reconciled. "
        "Live -644.8 is a valid current LIVE_ACCOUNT rate observation; -488.7 remains preserved USER_REPORTED. "
        "Proving account-specific overnight financing economics for execution gating still requires "
        "a genuine overnight position/deal showing charged swap — not forced selection of one metadata value."
    )

    out = {
        "dimension": "swap",
        "current_state": UNKNOWN_FOR_EXECUTION,
        "forensic_table": rows,
        "delta_long": SWAP_LONG_PHASE64_7 - SWAP_LONG_PHASE63,
        "overwrite": False,
        "interchangeable": False,
        "reconciled": reconciled,
        "conflict_status": conflict_status,
        "hypotheses": hypotheses,
        "swap_mode": SWAP_MODE_POINTS,
        "swap_rollover3days": SWAP_ROLLOVER3DAYS,
        "execution_policy": execution_policy,
        "classification": classification,
        "reasoning": reasoning,
        "can_close_without_fill": False,
        "next_evidence": (
            "Genuine overnight XAUUSDm deal(s) with swap field on this account, "
            "and/or dated broker swap-history for XAUUSDm proving when -488.7 became -644.8"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
