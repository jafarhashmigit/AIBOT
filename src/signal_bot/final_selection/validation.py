"""Validation ledger for Prompt9 — records what was and was not run."""

from __future__ import annotations

from typing import Any

from signal_bot.final_selection.constants import COST_MODEL_VERSION


def build_validation_results(
    *,
    c07: dict[str, Any],
    economics: dict[str, Any],
    live: dict[str, Any],
) -> dict[str, Any]:
    return {
        "confirmatory_protocol": {
            "chronological_train_validation": "NOT_RUN — no implementable frozen candidate",
            "date_blocked_evaluation": "NOT_RUN",
            "random_candle_split": False,
            "lookahead_prevention": "N/A — no replay",
            "overlapping_trade_control": "N/A",
            "phase58_holdout_accessed": False,
        },
        "c07_a": {
            "disposition": c07.get("disposition"),
            "confirmatory_validation_run": c07.get("confirmatory_validation_run"),
            "exploratory_archive_screen_authorized": c07.get("exploratory_archive_screen_authorized"),
            "n_trades": c07.get("n_trades"),
            "buy_sell_separate": "N/A",
            "expectancy_gross_r": c07.get("expectancy_gross_r"),
            "expectancy_net_r": c07.get("expectancy_net_r"),
            "profit_factor": None,
            "max_drawdown_r": None,
            "win_rate": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "holding_time": None,
            "exposure": None,
            "date_blocked_ci": None,
            "walk_forward": "NOT_RUN — insufficient independent data and unimplementable rules",
            "beats_WAIT": None,
            "parameter_stability": "NOT_DEMONSTRATED — parameters not evidence-frozen",
            "NET_PROFITABILITY": c07.get("NET_PROFITABILITY"),
        },
        "h70_reference_not_revived": {
            "note": "Prompt4 already challenged; expectancy_gross_r≈−0.228R on 6 trades; excluded",
        },
        "cost_integration": {
            "cost_model_version": COST_MODEL_VERSION,
            "NET_PROFITABILITY": economics.get("NET_PROFITABILITY"),
            "unknown_commission_treated_as_zero": False,
            "conflicted_swap_treated_as_zero": False,
            "unverified_slippage_treated_as_zero": False,
            "gross_vs_net": "Net cannot be established; gross not used to force qualification",
        },
        "live_sample": {
            "complete_independent_dates": live.get("n_complete_independent_live_dates"),
            "live_m5": live.get("unique_newly_closed_live_m5_bars"),
            "quotes": live.get("live_quote_observations"),
        },
        "baseline_WAIT": {
            "expectancy_r": 0.0,
            "note": "Abstention baseline; no candidate beat WAIT under confirmatory protocol",
        },
    }


def build_cost_and_risk_assessment(economics: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    return {
        "cost_model_version": COST_MODEL_VERSION,
        "spread": {
            "status": "PARTIALLY_VERIFIED" if economics.get("spread_n") else "UNKNOWN",
            "n": economics.get("spread_n"),
            "median_price": economics.get("spread_median_price"),
        },
        "commission": "UNKNOWN",
        "swap": "CONFLICTED",
        "slippage": "UNKNOWN",
        "gap_stop_risk": "UNKNOWN",
        "NET_PROFITABILITY": economics.get("NET_PROFITABILITY"),
        "production_cost_model_approved": False,
        "risk_policy": "UNAPPROVED",
        "risk_approval_blockers": [
            "No qualified strategy with validated expectancy",
            "Commission unknown",
            "Swap conflicted",
            "Slippage unverified",
            "Independent live sample inadequate",
        ],
        "discord_actionable": selection.get("discord_actionable"),
        "unknown_costs_as_zero": False,
    }
