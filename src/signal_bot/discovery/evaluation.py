"""Candidate evaluation — exploratory only; no sealed holdout; costs ≠ 0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_bot.discovery.constants import EVIDENCE_CLASS, PROJECT_ROOT


def load_h70_prompt04_stats() -> dict[str, Any]:
    path = PROJECT_ROOT / "reports" / "completion" / "PROMPT_04_CHALLENGE_BUNDLE.json"
    if not path.is_file():
        return {"available": False}
    blob = json.loads(path.read_text(encoding="utf-8"))
    stats = blob.get("stats") or {}
    return {
        "available": True,
        "strategy": "H70_LS1 (excluded from revival)",
        "n_trades": blob.get("n_trades") or stats.get("total_realized_trades"),
        "n_independent_dates": stats.get("n_dates_with_trades"),
        "buy_sell": {"n_buy": stats.get("n_buy"), "n_sell": stats.get("n_sell")},
        "expectancy_gross_r": stats.get("expectancy_gross_r"),
        "profit_factor_gross": stats.get("profit_factor_gross") or stats.get("profit_factor"),
        "win_rate": stats.get("win_rate"),
        "max_dd_r": stats.get("max_drawdown_r"),
        "date_blocked_ci95": (stats.get("date_blocked_daily_expectancy") or {}).get("ci95"),
        "evidence_class": EVIDENCE_CLASS,
        "net_profitability": stats.get("net_profitability") or "NOT_ESTABLISHED",
        "note": "Unknown costs never treated as zero; sample too small for inference",
    }


def build_statistical_evaluation(selection: dict[str, Any], feasibility: dict[str, Any]) -> dict[str, Any]:
    """No new candidate evaluated on archive as 'promising' — document why."""
    h70 = load_h70_prompt04_stats()
    complete = int(
        (feasibility.get("genuine_live_exness_xauusdm") or {}).get(
            "independent_complete_asia_london_dates"
        )
        or 0
    )
    return {
        "evidence_class": EVIDENCE_CLASS,
        "candidates_statistically_evaluated_as_new_edge": 0,
        "reason": (
            "No candidate selected for formal screen. Independent complete live dates="
            f"{complete}. Evaluating C07_A on consumed Phase53 would be "
            "EXPLORATORY_RETROSPECTIVE_ONLY and risks multiple-testing reuse of the same archive "
            "already used for H70/Phase45. Protocol: withhold archive optimization."
        ),
        "h70_reference_only_not_revived": h70,
        "selection_verdict": selection.get("primary_verdict"),
        "gross_expectancy_new_candidate": None,
        "profit_factor_new_candidate": None,
        "date_blocked_ci": None,
        "monthly_consistency": None,
        "execution_ambiguity": "N/A — no frozen candidate",
        "cost_sensitivity": {
            "spread": "UNKNOWN → net NOT_ESTABLISHED",
            "commission": "UNKNOWN",
            "swap": "UNKNOWN",
            "slippage": "UNKNOWN",
            "unknown_costs_treated_as_zero": False,
        },
        "independent_profitability_evidence": False,
        "multiple_testing_control": (
            "All Prompt7 hypotheses preregistered; rejected families not re-screened; "
            "no holdout peek; no random train/test"
        ),
        "phase58_holdout_accessed": False,
    }


def dual_experience_architecture_note() -> dict[str, Any]:
    return {
        "source_1_historical_hypothetical": {
            "description": "Replay BUY/SELL outcomes on historical bars (what-if)",
            "must_not_label_as": "paper trading experience",
            "storage_hint": "Separate ledger / experience store key: historical_hypothetical",
        },
        "source_2_actual_paper_decisions": {
            "description": "AIBOT paper lifecycle decisions (Phase54/56) and outcomes",
            "must_not_mix_with": "historical_hypothetical",
            "storage_hint": "paper_decision_experience",
        },
        "learning_claim_policy": (
            "Do not claim learning improves performance without independent OOS evidence. "
            "With Champion NO_MODEL and production WAIT, no online learner updates production."
        ),
        "if_future_candidate_survives": (
            "Consume experiences as separate features/labels with provenance tags; "
            "never train on sealed holdout; never use same dates for discovery and confirmation."
        ),
    }
