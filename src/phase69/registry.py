"""Hypothesis preregistration registry — immutable after freeze."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase69.constants import REGISTRY_PATH, REGISTRY_VERSION, RECIPE_ID, canonical_json_sha256


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hypotheses() -> list[dict[str, Any]]:
    return [
        {
            "id": "H69_D1_DISPLACEMENT_COMPETING_OUTCOMES",
            "research_question": (
                "After a predefined displacement event, does continuation or reversal show "
                "reproducible directional predictive information?"
            ),
            "rule_definitions": {
                "displacement": "abs(close[t]-close[t-1])/ATR14[t] >= 1.5",
                "buy_sell_separation": True,
                "horizons_m5": [1, 3, 6, 12, 24],
                "competing_outcomes": "continuation vs reversal on same event (not 2N samples)",
                "path_metrics": ["MFE", "MAE", "MFE_ATR", "MAE_ATR", "time_to_threshold"],
                "date_level_dependence": True,
            },
            "unresolved_definitions": [],
            "primary_outcome": "date-blocked mean direction-adjusted end_return_atr at horizon 12 vs WAIT baseline",
            "secondary_outcomes": ["p_continuation", "p_reversal", "MFE/MAE distributions", "vol-regime splits"],
            "baseline_control": "WAIT (net_r=0 abstention); unconditional same-session move",
            "required_sample_rationale": (
                "≥20 Exness OPEN independent date-blocks discovery + ≥10 validation; "
                "Phase68 archive exploratory (28 events) is NOT confirmation"
            ),
            "statistical_methodology": (
                "Date-block bootstrap CIs; event-stride overlap controls; BUY/SELL separate; "
                "Bonferroni within family; no threshold optimization after freeze"
            ),
            "multiple_testing_family": "H69_DISPLACEMENT_FAMILY",
            "cost_assumptions": {
                "spread": "use Exness observed quotes when available",
                "commission": "UNKNOWN",
                "swap": "UNKNOWN_FOR_EXECUTION",
                "slippage": "UNKNOWN",
                "never_zero_unknowns": True,
            },
            "discovery_validation_eligibility": "Exness XAUUSDm live BROKER_OBSERVED_* only; archive exploratory excluded from confirmation",
            "rejection_criteria": [
                "Fails vs WAIT after cost stress",
                "BUY/SELL inconsistency without preregistered asymmetry hypothesis",
                "No date-block CI excluding zero under declared alpha",
            ],
            "status": "PREREGISTERED_UNVALIDATED",
            "phase68_is_confirmation": False,
        },
        {
            "id": "H69_LS1_ASIA_SWEEP_LONDON_MSS",
            "research_question": (
                "Does an objectively defined Asia-range sweep followed by an opposite-direction "
                "London M5 structure break provide incremental predictive information?"
            ),
            "rule_definitions": {
                "label": "OUR_PREREGISTERED_VARIANT",
                "not_original_video_strategy": True,
                "timezone_note": "Must use explicit IANA zones with DST-aware conversion",
            },
            "unresolved_definitions": [
                "Asia session boundaries (IANA)",
                "Pre-London sweep window",
                "Sweep buffer",
                "Re-entry condition",
                "Swing confirmation / MSS definition",
                "London first-hour boundaries",
                "Entry timing",
                "Stop placement",
                "Setup expiration",
            ],
            "primary_outcome": "TBD after definitions freeze — directional expectancy vs WAIT",
            "secondary_outcomes": ["hit-rate", "MFE/MAE", "session coverage"],
            "baseline_control": "WAIT; random same-session entries",
            "required_sample_rationale": "Deferred until definitions frozen; expect ≥30 independent Exness dates due to rarity",
            "statistical_methodology": "Date-blocked; preregister all parameters before first Exness evaluation",
            "multiple_testing_family": "H69_SESSION_STRUCTURE_FAMILY",
            "cost_assumptions": {
                "commission": "UNKNOWN",
                "swap": "UNKNOWN_FOR_EXECUTION",
                "slippage": "UNKNOWN",
                "never_zero_unknowns": True,
            },
            "discovery_validation_eligibility": "Exness live only after definition freeze",
            "rejection_criteria": ["Definitions remain unresolved at evaluation time", "Fails cost-stressed OOS"],
            "status": "PREREGISTERED_UNVALIDATED_DEFINITIONS_UNRESOLVED",
            "original_creator_settings_available": False,
        },
        {
            "id": "H69_US1_US_OPENING_RANGE_BREAKOUT",
            "research_question": (
                "Does a fixed US opening-range breakout with M5 confirmation offer predictive "
                "information beyond unconditional session movement?"
            ),
            "rule_definitions": {
                "timezone": "America/New_York",
                "dst_aware": True,
                "label": "OUR_PREREGISTERED_VARIANT",
                "not_validated_video_results": True,
            },
            "unresolved_definitions": [
                "Opening range duration (e.g. 15/30/60 minutes) — must freeze before test",
                "Breakout confirmation rule",
                "Entry timing",
                "Stop and target",
                "Expiration",
            ],
            "primary_outcome": "OR breakout direction expectancy vs unconditional US-session move and WAIT",
            "secondary_outcomes": ["false-break rate", "MFE/MAE", "spread-conditioned outcomes"],
            "baseline_control": "WAIT; buy/sell unconditional at OR end",
            "required_sample_rationale": "≥25 independent Exness US-session dates discovery + ≥10 validation",
            "statistical_methodology": "Date-blocked; DST-aware session clocks; no post-hoc OR length search",
            "multiple_testing_family": "H69_SESSION_STRUCTURE_FAMILY",
            "cost_assumptions": {
                "commission": "UNKNOWN",
                "swap": "UNKNOWN_FOR_EXECUTION",
                "slippage": "UNKNOWN",
                "never_zero_unknowns": True,
            },
            "discovery_validation_eligibility": "Exness live only",
            "rejection_criteria": ["Unresolved OR duration at eval", "No edge vs unconditional session baseline after costs"],
            "status": "PREREGISTERED_UNVALIDATED_DEFINITIONS_UNRESOLVED",
            "video_advertised_results_assumed_valid": False,
        },
    ]


def build_and_freeze_registry() -> dict[str, Any]:
    body = {
        "registry_version": REGISTRY_VERSION,
        "recipe_id": RECIPE_ID,
        "preregistered_at_utc": _utc(),
        "frozen_before_evaluation": True,
        "confirmatory_tests_run": False,
        "strategy_promotion": False,
        "champion_implication": "NO_MODEL_unless_future_gates",
        "production_implication": "WAIT",
        "amendment_policy": "Only via new registry_version; prior freeze immutable",
        "hypotheses": _hypotheses(),
        "n": 3,
    }
    body["registry_sha256"] = canonical_json_sha256({k: v for k, v in body.items() if k != "registry_sha256"})
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REGISTRY_PATH.is_file():
        prev = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if prev.get("registry_sha256") == body["registry_sha256"]:
            return prev
        if prev.get("frozen_before_evaluation") and prev.get("registry_version") == REGISTRY_VERSION:
            # Immutable: return existing
            return prev
    REGISTRY_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return body


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError("hypothesis_registry_not_frozen")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
