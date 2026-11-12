"""Consolidated candidate/evidence matrix from Prompts 1–8 and Phase30–69."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_bot.discovery.audit import build_research_audit
from signal_bot.discovery.data_feasibility import build_data_feasibility
from signal_bot.execution_economics.cost_model import build_cost_model
from signal_bot.execution_economics.evidence_qualification import build_live_evidence_qualification
from signal_bot.execution_economics.spread_analysis import analyze_live_spreads
from signal_bot.final_selection.constants import (
    ACTIVE_SYMBOL,
    ARCHIVE_SYMBOL,
    COST_MODEL_VERSION,
    PROJECT_ROOT,
    REPORTS,
)


def _load(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_candidate_evidence_matrix() -> dict[str, Any]:
    research = build_research_audit()
    feas = build_data_feasibility()
    live_q = build_live_evidence_qualification()
    spread = analyze_live_spreads()
    dist = spread.get("distribution_price_units") or {}
    dist_pts = spread.get("distribution_points") or {}
    cost = build_cost_model(
        observed_spread_price_median=dist.get("median"),
        observed_spread_points_median=dist_pts.get("median"),
        spread_n=int(spread.get("n_usable_quotes") or 0),
        commission_status="UNKNOWN",
        swap_status="CONFLICTED",
    )

    p04 = _load(REPORTS / "PROMPT_04_CHALLENGE_BUNDLE.json") or {}
    p07 = _load(REPORTS / "PROMPT_07_CANDIDATE_REGISTRY.json") or {}
    p08 = _load(REPORTS / "PROMPT_08_BUNDLE.json") or {}

    rows = [
        {
            "id": "NullPolicy",
            "family": "production_default",
            "status": "ACTIVE_PRODUCTION",
            "symbol": ACTIVE_SYMBOL,
            "evidence": "Phase54 WAIT",
            "eligible_for_prompt09_champion": False,
            "reason": "Abstention baseline — not a trading edge",
        },
        {
            "id": "H70_LS1_ASIA_SWEEP_LONDON_MSS",
            "family": "asia_london_mss",
            "status": "EXPLORATORY_NEGATIVE_INSUFFICIENT_SAMPLE",
            "symbol": ARCHIVE_SYMBOL,
            "n_trades": (p04.get("n_trades")),
            "expectancy_gross_r": (p04.get("stats") or {}).get("expectancy_gross_r"),
            "eligible_for_prompt09_champion": False,
            "reason": "Prompt4 exploratory negative; retune forbidden",
        },
        {
            "id": "C07_A_SESSION_OPEN_DISCOVERY",
            "family": "london_session_open",
            "status": "HELD_PROMPT07_NOT_ENGINEERED",
            "symbol": ACTIVE_SYMBOL,
            "eligible_for_prompt09_champion": "CONDITIONAL",
            "reason": "Only held Prompt7 hypothesis; must pass objective freeze + independent validation",
        },
        {
            "id": "H13_C",
            "family": "pullback",
            "status": "RETIRED_DO_NOT_REVIVE",
            "eligible_for_prompt09_champion": False,
            "reason": "Phase45 retired",
        },
        {
            "id": "mean_reversion",
            "family": "mean_reversion",
            "status": "RETIRED_EDGE_REJECTED",
            "eligible_for_prompt09_champion": False,
            "reason": "Retired",
        },
        {
            "id": "H42_A_VOL_COMPRESS_EXPAND",
            "family": "vol_compress_expand",
            "status": "REJECTED",
            "eligible_for_prompt09_champion": False,
            "reason": "do_not_revive",
        },
        {
            "id": "H42_C_SESSION_SWEEP_REJECT",
            "family": "failed_auction_sweep",
            "status": "REJECTED",
            "eligible_for_prompt09_champion": False,
            "reason": "sign-flip / do_not_revive; near H70 theme",
        },
        {
            "id": "H69_D1 / H69_US1",
            "family": "displacement / US_ORB",
            "status": "PREREGISTERED_UNVALIDATED_OR_UNRESOLVED",
            "eligible_for_prompt09_champion": False,
            "reason": "Unresolved defs and/or archive not confirmation; no independent live sample",
        },
    ]

    return {
        "accepted_validated_edges": [],
        "n_accepted_validated_edges": 0,
        "champion_current": "NO_MODEL",
        "production_policy": "phase54_null_policy_v1",
        "matrix_rows": rows,
        "retired_do_not_revive_n": research.get("n_retired_do_not_revive"),
        "phase45_rejected_n": research.get("n_rejected_phase45"),
        "prompt07_verdict": p07.get("primary_verdict"),
        "prompt08_verdict": p08.get("primary_verdict"),
        "data": {
            "live_symbol": ACTIVE_SYMBOL,
            "live_m5": live_q.get("unique_newly_closed_live_m5_bars"),
            "live_quotes": live_q.get("live_quote_observations"),
            "complete_independent_asia_london_dates": live_q.get("n_complete_independent_live_dates"),
            "archive_symbol": ARCHIVE_SYMBOL,
            "phase53_eligible_consumed_days": (feas.get("metaquotes_xauusd_archives") or {}).get(
                "n_eligible_consumed"
            ),
            "archive_independent_confirmation": False,
            "phase58_holdout_accessed": False,
            "symbol_difference_note": (
                f"{ARCHIVE_SYMBOL} MetaQuotes demo archive ≠ {ACTIVE_SYMBOL} Exness live; "
                "must not be treated as identical for confirmatory validation"
            ),
        },
        "execution_economics": {
            "cost_model_version": COST_MODEL_VERSION,
            "NET_PROFITABILITY": cost.get("NET_PROFITABILITY"),
            "production_approved": cost.get("production_approved"),
            "spread_n": spread.get("n_usable_quotes"),
            "spread_median_price": dist.get("median"),
            "commission": "UNKNOWN",
            "swap": "CONFLICTED",
            "slippage": "UNKNOWN",
        },
        "phase58_holdout_sealed": research.get("phase58_holdout_sealed"),
        "feasibility_evidence_class": feas.get("evidence_class_for_discovery"),
    }
