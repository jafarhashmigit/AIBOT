"""Consolidated research audit — no holdout access; no strategy revival."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_bot.discovery.constants import PROJECT_ROOT, H70_STATUS


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_research_audit() -> dict[str, Any]:
    phase45 = _load_json(PROJECT_ROOT / "reports" / "phase45" / "consolidated_experiment_registry.json") or {}
    phase69 = _load_json(PROJECT_ROOT / "reports" / "phase69" / "hypothesis_registry.json") or {}
    phase58 = _load_json(PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json") or {}
    h70 = _load_json(PROJECT_ROOT / "reports" / "completion" / "H70_LS1_hypothesis_registry.json") or {}
    p04 = _load_json(PROJECT_ROOT / "reports" / "completion" / "PROMPT_04_CHALLENGE_BUNDLE.json") or {}

    retired = list(phase45.get("retired_do_not_revive") or [])
    rejected_hyps = [
        {
            "id": h.get("id"),
            "family": h.get("family"),
            "status": h.get("status"),
            "do_not_revive": h.get("do_not_revive"),
            "rejection_reasons": h.get("rejection_reasons"),
        }
        for h in (phase45.get("hypotheses") or [])
    ]

    preregistered = []
    for h in phase69.get("hypotheses") or []:
        preregistered.append(
            {
                "id": h.get("id"),
                "status": h.get("status"),
                "unresolved_definitions": h.get("unresolved_definitions") or [],
                "phase68_is_confirmation": h.get("phase68_is_confirmation"),
            }
        )

    excluded_families = {
        "pullback_H13_C": "RETIRED do_not_revive",
        "mean_reversion": "RETIRED EDGE_REJECTED",
        "vol_compress_expand_H42_A": "REJECTED — do not revive under new name",
        "session_sweep_reject_H42_C": "REJECTED sign-flip; near H70 theme",
        "displacement_H42_J_H44_2_H69_D1_archive": "Rejected or exploratory-only; archive not confirmation",
        "asia_london_mss_H70": f"{H70_STATUS}; gross expectancy negative on 6 trades",
        "ny_drift_H42_H": "REJECTED",
        "range_break_H42_D": "REJECTED zero events",
    }

    return {
        "accepted_validated_edge_hypotheses": [],
        "n_accepted": 0,
        "active_production_policy": "phase54_null_policy_v1 (WAIT)",
        "champion": "NO_MODEL",
        "preregistered_unvalidated": preregistered,
        "rejected_phase45": rejected_hyps,
        "n_rejected_phase45": len(rejected_hyps),
        "retired_do_not_revive": retired,
        "n_retired_do_not_revive": len(retired),
        "h70": {
            "id": h70.get("hypothesis_id") or "H70_LS1_ASIA_SWEEP_LONDON_MSS",
            "status": H70_STATUS,
            "prompt04_n_trades": p04.get("n_trades"),
            "prompt04_expectancy_gross_r": (p04.get("stats") or {}).get("expectancy_gross_r"),
            "prompt04_profit_factor_gross": (p04.get("stats") or {}).get("profit_factor_gross"),
            "prompt04_verdict": "INSUFFICIENT_SAMPLE / exploratory negative gross vs WAIT",
            "revive_forbidden": True,
        },
        "excluded_families_for_prompt07": excluded_families,
        "phase58_holdout_sealed": list(phase58.get("holdout_sealed") or []),
        "phase58_holdout_accessed": False,
        "previously_tested_feature_themes": [
            "ATR displacement",
            "volatility compression/expansion",
            "session sweep / liquidity grab",
            "Asia–London structure (H70)",
            "trend exhaustion / wick",
            "MTF momentum disagreement",
            "tick imbalance",
            "NY session drift",
            "prev-day level rejection",
            "mean reversion z/RSI",
            "pullback continuation (H13_C)",
        ],
        "unvalidated_candidates_not_to_confirm_on_archive": [
            "H69_D1_DISPLACEMENT_COMPETING_OUTCOMES",
            "H69_LS1 (superseded definitions via H70; H70 failed exploratory)",
            "H69_US1_US_OPENING_RANGE_BREAKOUT (definitions unresolved)",
        ],
        "note": "No accepted edge. Discovery must not rename rejected families.",
    }
