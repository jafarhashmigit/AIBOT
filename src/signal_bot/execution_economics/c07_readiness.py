"""C07_A readiness prerequisites — do not implement or evaluate the strategy."""

from __future__ import annotations

from typing import Any

from signal_bot.execution_economics.constants import TARGET_COMPLETE_LIVE_DATES


def build_c07_a_readiness() -> dict[str, Any]:
    return {
        "candidate_id": "C07_A_SESSION_OPEN_DISCOVERY",
        "status": "HOLD_FOR_DATA_NOT_IMPLEMENTED",
        "strategy_implemented": False,
        "screened_on_consumed_archives": False,
        "h70_revived": False,
        "missing_from_original_discovery_rationale": [
            "Exact opening-range bar count N (15 vs 30 vs 60 minutes) not frozen",
            "Buffer definition (absolute vs ATR multiple) not frozen",
            "Acceptance rule (close beyond OR vs wick vs multi-bar) not frozen",
            "Whether Asia mid or OR mid is the reference for 'acceptance' not specified",
            "News-filter / high-impact calendar exclusion undefined",
            "Maximum OR width vs ATR invalidation threshold undefined",
            "BUY/SELL asymmetry (if any) not preregistered",
        ],
        "prerequisites_before_preregistration_and_evaluation": {
            "exact_market_mechanism": (
                "London open inventory rebalancing → first N M5 bars define opening range (OR); "
                "acceptance = closed bar beyond OR extreme by buffer implies continuation into London AM."
            ),
            "objective_mathematical_definitions_required": [
                "N = number of M5 bars in OR (integer)",
                "buffer = max(abs_floor, k * ATR14) with fixed abs_floor and k",
                "BUY iff close > OR_high + buffer on first confirmation bar after OR complete",
                "SELL iff close < OR_low - buffer on first confirmation bar after OR complete",
                "WAIT otherwise",
                "SL = opposite OR extreme ± sl_buffer",
                "TP = entry ± reward_risk * risk_distance",
                "signal_expiry_bars, max_hold_bars integers",
            ],
            "frozen_timezone_and_session_rules": {
                "london_tz": "Europe/London (IANA, DST-aware)",
                "or_start": "London 08:00 local",
                "or_end": "or_start + N*5 minutes",
                "trading_window_end": "must freeze (e.g. London 12:00)",
                "bar_timestamp_semantics": "closed-bar only; forming bars forbidden",
            },
            "required_data_resolution": "Exness XAUUSDm closed M5 + live bid/ask for spread conditioning",
            "minimum_eligible_sample": {
                "independent_complete_asia_london_or_london_open_dates": TARGET_COMPLETE_LIVE_DATES,
                "minimum_realized_trades_for_exploratory_screen": 40,
                "minimum_date_blocks": 10,
                "note": "Live Exness only for confirmation; consumed MetaQuotes archives exploratory-only and not for selection",
            },
            "statistical_protocol": [
                "Preregister rules before evaluating outcomes",
                "Chronological / date-blocked splits only",
                "Date-block bootstrap CI for expectancy vs WAIT",
                "Report BUY/SELL separately",
                "No random train/test",
                "No Phase58 holdout access",
            ],
            "multiple_testing_controls": [
                "Single primary outcome: date-blocked mean gross R vs WAIT",
                "Bonferroni within C07 family if multiple variants",
                "Record all variants considered including rejected",
            ],
            "cost_model_requirements": [
                "Use prompt08_exness_xauusdm_cost_model_v1 once approved components allow",
                "Apply observed spread as known-cost adjustment when sample adequate",
                "Commission/swap/slippage remain UNKNOWN → NET_PROFITABILITY=NOT_ESTABLISHED",
                "Do not assume zero costs",
                "High cost sensitivity expected at London open — require spread regime reporting",
            ],
            "independent_validation_protocol": [
                "Discovery on early live dates only after freeze",
                "Validation on later live dates never used in discovery",
                "No retuning after validation peek",
                "Champion remains NO_MODEL until confirmatory gates pass",
            ],
        },
        "current_blockers": [
            "0 complete independent Asia+London live dates",
            "Cost model not production-approved (commission/swap/slippage unresolved)",
            "Objective parameters for C07_A not frozen",
        ],
    }
