"""Preregister H70_LS1 freeze record — no performance evaluation in this module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from signal_bot.asia_london_mss import constants as C


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_registry_record() -> dict[str, Any]:
    return {
        "hypothesis_id": C.HYPOTHESIS_ID,
        "registry_version": "completion_h70_ls1_v1",
        "preregistered_at_utc": _utc(),
        "frozen_before_evaluation": True,
        "confirmatory_tests_run": False,
        "strategy_promotion": False,
        "champion_implication": "NO_MODEL",
        "production_implication": "WAIT",
        "parameter_label": C.PARAMETER_LABEL,
        "original_creator_settings_available": False,
        "not_original_video_strategy": True,
        "differs_from": {
            "H69_LS1_ASIA_SWEEP_LONDON_MSS": "Same research question; H69 left definitions unresolved. H70 freezes PROJECT_PREREGISTERED_PARAMETERS.",
            "H42_C_SESSION_SWEEP_REJECT": "Rejected family screen without frozen Asia IANA range + London MSS state machine + product SL/TP.",
            "H13_C": "Retired pullback model — unrelated.",
            "H69_D1": "Displacement ATR event family — excluded.",
            "mean_reversion": "Retired — excluded.",
        },
        "rationale": (
            "Session liquidity grab of Asia range then opposite-direction London M5 market "
            "structure shift may encode stop-run + institutional continuation information."
        ),
        "parameters": {
            "symbol": C.SYMBOL,
            "timeframe": C.TIMEFRAME,
            "asia_tz": C.ASIA_TZ,
            "asia_start_hm": C.ASIA_START_HM,
            "asia_end_hm": C.ASIA_END_HM,
            "london_tz": C.LONDON_TZ,
            "london_start_hm": C.LONDON_START_HM,
            "london_end_hm": C.LONDON_END_HM,
            "min_asia_bars": C.MIN_ASIA_BARS,
            "min_asia_range_abs": C.MIN_ASIA_RANGE_ABS,
            "max_asia_range_atr": C.MAX_ASIA_RANGE_ATR,
            "sweep_buffer_atr": C.SWEEP_BUFFER_ATR,
            "sweep_buffer_abs_min": C.SWEEP_BUFFER_ABS_MIN,
            "require_close_back_inside": C.REQUIRE_CLOSE_BACK_INSIDE,
            "sweep_to_mss_max_bars": C.SWEEP_TO_MSS_MAX_BARS,
            "swing_left": C.SWING_LEFT,
            "swing_right": C.SWING_RIGHT,
            "reward_risk": C.REWARD_RISK,
            "min_reward_risk": C.MIN_REWARD_RISK,
            "sl_buffer_atr": C.SL_BUFFER_ATR,
            "signal_expiry_bars": C.SIGNAL_EXPIRY_BARS,
            "max_hold_bars": C.MAX_HOLD_BARS,
        },
        "entry_rules_summary": (
            "After completed Asia range, detect sweep beyond high/low with close back inside; "
            "then in London morning window require closed-bar MSS (fractal swing break); "
            "enter on MSS confirmation bar close."
        ),
        "exit_rules_summary": (
            f"SL beyond sweep extreme + buffer; TP at {C.REWARD_RISK}R; "
            f"signal expiry {C.SIGNAL_EXPIRY_BARS} bars; max hold {C.MAX_HOLD_BARS} bars."
        ),
        "data_requirements": "Closed XAUUSDm M5 bars with UTC timestamps; ATR(14) available",
        "failure_conditions": [
            "Incomplete Asia session",
            "No valid sweep",
            "No London MSS within window",
            "Forming bar",
            "ATR unavailable",
            "Invalid stop distance",
        ],
        "known_limitations": [
            "Parameters are project-preregistered, not creator-authenticated",
            "No costed edge validation in Prompt 3",
            "Consumed archives must not be used as independent discovery",
            "Commission/swap UNKNOWN — never treated as zero",
        ],
        "planned_validation": "Exness-native BROKER_OBSERVED_* date-blocked evaluation in later prompts",
        "status": "PREREGISTERED_DEFINITIONS_FROZEN_UNVALIDATED",
    }


def freeze_to_disk() -> dict[str, Any]:
    body = build_registry_record()
    C.REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    C.REGISTRY_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return body
