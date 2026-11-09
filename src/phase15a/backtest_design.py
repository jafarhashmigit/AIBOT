"""Part D — independent backtesting methodology (design only; not executed)."""

from __future__ import annotations

from typing import Any


def backtest_design() -> dict[str, Any]:
    return {
        "design_id": "phase15a_independent_backtest_v1",
        "executed": False,
        "profitability_calculated": False,
        "uses_real_telegram_messages": False,
        "principles": [
            "Signal publication time determines earliest eligible entry.",
            "Never use price movement that occurred before publication.",
            "Distinguish market entry from limit/zone entry.",
            "Unfilled entries recorded as NOT_FILLED.",
            "Include spread and conservative slippage.",
            "Model partial exits separately.",
            "Resolve ambiguous same-candle SL/TP cases conservatively (assume adverse).",
            "Preserve all signal updates chronologically.",
            "Do not assume a trade closed because the provider posted a winning result.",
            "Include unresolved and missing outcomes.",
            "Compare providers separately; no pooled champion claim.",
        ],
        "eligibility": {
            "earliest_entry_rule": "published_at_utc",
            "pre_publication_prices": "FORBIDDEN_FOR_ENTRY_AND_FILL",
            "instrument_filter": "XAUUSD_ONLY",
            "permission_gate": "permission_reference required before any real-signal run",
        },
        "entry_model": {
            "MARKET": {
                "fill_rule": "Next eligible bar open after published_at_utc, plus buy/sell slippage and half-spread.",
                "if_no_bar": "NOT_FILLED",
            },
            "LIMIT_ZONE": {
                "fill_rule": (
                    "Fill only if post-publication price trades through the zone "
                    "[entry_min, entry_max] in the trade direction; fill at adverse edge of zone + slippage."
                ),
                "expiry": "Use signal cancel/update or configured max holding window; else NOT_FILLED.",
                "if_never_touched": "NOT_FILLED",
            },
            "UNKNOWN": {
                "fill_rule": "Do not fabricate fills; mark AMBIGUOUS / NOT_EVALUATED.",
            },
        },
        "costs": {
            "spread_model": "Conservative fixed or bar-based spread in price units (configured later).",
            "slippage_model": "Conservative adverse slippage on entry and on each exit tranche.",
            "commission": "Optional; default include if broker profile known, else zero with explicit note.",
        },
        "exit_model": {
            "stop_loss": "Intrabar breach after fill; use update history for modified SL effective times.",
            "take_profit_levels": "Partial exits at each TP; remaining size continues.",
            "same_candle_sl_tp": "CONSERVATIVE_ADVERSE — assume SL hit before TP when both possible in one bar.",
            "provider_claimed_win": "IGNORED — independent price path only.",
            "cancel_before_fill": "NOT_FILLED",
            "cancel_after_fill": "Close at next eligible open + costs; tag CANCELLED_EXIT.",
        },
        "outcomes": {
            "filled_statuses": ["FILLED_OPEN", "FILLED_CLOSED", "FILLED_PARTIAL"],
            "unfilled_status": "NOT_FILLED",
            "ambiguous_status": "AMBIGUOUS_NOT_EVALUATED",
            "incomplete_status": "INCOMPLETE_NOT_EVALUATED",
            "unresolved_status": "UNRESOLVED",
            "missing_price_status": "MISSING_MARKET_DATA",
        },
        "reporting": {
            "per_provider_only": True,
            "metrics_when_authorized": [
                "n_signals",
                "n_filled",
                "n_not_filled",
                "n_ambiguous",
                "n_incomplete",
                "n_unresolved",
                "expectancy_filled_only",
                "max_drawdown_filled_only",
                "partial_exit_breakdown",
            ],
            "forbid_profitability_from_unauthorized_or_incomplete_samples": True,
        },
        "data_separation": {
            "source_type": "EXTERNAL_PROVIDER_SIGNAL",
            "must_not_merge_with": [
                "HISTORICAL_HYPOTHETICAL",
                "AGENT_PAPER",
                "FORWARD_SHADOW",
            ],
        },
        "execution_gate": {
            "requires": [
                "written_permission_or_authorized_export",
                "normalized_signals_with_provenance",
                "independent_market_data_within_research_cutoff",
            ],
            "phase15a_allowed_to_execute": False,
        },
    }
