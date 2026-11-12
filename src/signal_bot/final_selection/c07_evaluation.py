"""C07_A evaluation — attempt objective freeze; reject if evidence cannot specify rules."""

from __future__ import annotations

from typing import Any

from signal_bot.execution_economics.c07_readiness import build_c07_a_readiness
from signal_bot.final_selection.constants import (
    ACTIVE_SYMBOL,
    MIN_DATE_BLOCKS,
    MIN_INDEPENDENT_COMPLETE_LIVE_DATES,
    MIN_REALIZED_TRADES,
)


# Parameters that would need evidence-derived freeze — none are fixed in Prompt7 rationale.
UNRESOLVED_PARAMETERS = [
    "OR_N_BARS",  # 3 / 6 / 12 for 15/30/60m
    "BUFFER_ABS_FLOOR",
    "BUFFER_ATR_K",
    "ACCEPTANCE_RULE",  # close vs wick vs multi-bar
    "REFERENCE_MID",  # OR mid vs Asia mid
    "MAX_OR_WIDTH_ATR",
    "REWARD_RISK",
    "SL_BUFFER",
    "SIGNAL_EXPIRY_BARS",
    "MAX_HOLD_BARS",
    "TRADING_WINDOW_END",
    "NEWS_FILTER",
    "BUY_SELL_ASYMMETRY",
]


def evaluate_c07_a(*, live_complete_dates: int, live_m5: int) -> dict[str, Any]:
    readiness = build_c07_a_readiness()
    missing = list(readiness.get("missing_from_original_discovery_rationale") or [])

    # Can we derive exact measurable rules FROM EXISTING EVIDENCE (not invent)?
    evidence_derived_freeze_possible = False
    # Prompt7 sketch gave qualitative OR idea but not unique measurable values.
    # Inventing PROJECT_PREREGISTERED values would enable exploratory code but would
    # NOT constitute evidence-derived specification for confirmatory qualification.

    disposition = "REJECT_UNIMPLEMENTABLE"
    reason = (
        "C07_A cannot be specified objectively from available evidence: "
        f"{len(UNRESOLVED_PARAMETERS)} critical parameters unresolved in discovery rationale. "
        "Freezing arbitrary PROJECT_PREREGISTERED values would invent a strategy, not discover one. "
        "Prompt9 forbids arbitrary parameter invention and retuning rejected families."
    )

    # Even if implementable, independent confirmatory data floor
    data_blocks_qualification = live_complete_dates < MIN_INDEPENDENT_COMPLETE_LIVE_DATES

    exploratory_archive_screen_authorized = False
    # Consumed MetaQuotes XAUUSD is not eligible for champion confirmation;
    # screening without frozen evidence-derived rules is also unauthorized.

    return {
        "candidate_id": "C07_A_SESSION_OPEN_DISCOVERY",
        "symbol_required": ACTIVE_SYMBOL,
        "disposition": disposition,
        "implementable_from_evidence": evidence_derived_freeze_possible,
        "unresolved_parameters": UNRESOLVED_PARAMETERS,
        "missing_from_rationale": missing,
        "readiness_status": readiness.get("status"),
        "live_complete_asia_london_dates": live_complete_dates,
        "live_m5": live_m5,
        "min_complete_dates_required": MIN_INDEPENDENT_COMPLETE_LIVE_DATES,
        "min_trades_required": MIN_REALIZED_TRADES,
        "min_date_blocks_required": MIN_DATE_BLOCKS,
        "independent_data_insufficient": data_blocks_qualification,
        "exploratory_archive_screen_authorized": exploratory_archive_screen_authorized,
        "confirmatory_validation_run": False,
        "n_trades": 0,
        "expectancy_gross_r": None,
        "expectancy_net_r": None,
        "NET_PROFITABILITY": "NOT_ESTABLISHED",
        "reason": reason,
        "strategy_module_created": False,
    }
