"""Five primary hypotheses — distinct from Phase42 rejects and retired strategies."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from phase44.constants import MAX_HYPOTHESES, PHASE42_REJECTED_PREFIX, RECIPE_ID, RETIRED
from phase44.progress import write_json


def primary_hypotheses() -> list[dict[str, Any]]:
    hyps = [
        {
            "id": "H44_1_PREV_DAY_LEVEL_REJECTION",
            "family": "previous_session_level_rejection",
            "behavior": (
                "When price pierces the prior calendar-day high/low and closes back inside by ≥0.3 ATR, "
                "the next move tends to continue away from the pierced level (liquidity grab / rejection)."
            ),
            "not_phase42": "Uses prior calendar-day extremes, not rolling 12-bar sweep (H42_C).",
            "observable_inputs": ["prev_day_high", "prev_day_low", "pierce_reject", "atr_14"],
            "entry_condition": "pierce prev_day extreme AND close back inside by >=0.3 ATR",
            "directional_prediction": "AWAY_FROM_PIERCED_LEVEL",
            "horizon_bars": 12,
            "min_sample_discovery": 50,
            "success_criteria": "signed ret_atr_H12 effect >=0.12 on discovery; validate once with Bonferroni",
            "rejection_criteria": "effect<0.12 or discovery/validation sign flip or Bonferroni CI includes 0",
            "execution_cost_model": "BUY ask/SELL bid; TP1.5/SL1.0 ATR; H12 timeout",
            "decision_side": "AWAY_FROM_PIERCED",
        },
        {
            "id": "H44_2_DISPLACEMENT_CONTINUATION",
            "family": "displacement_continuation",
            "behavior": (
                "After a large single-bar displacement (|close-open|>=1.8 ATR) with close in upper/lower "
                "quartile of the bar, price tends to continue in displacement direction over H6 "
                "(impulse continuation), opposite of Phase42 retracement hypothesis."
            ),
            "not_phase42": "Opposite directional claim vs H42_J_DISPLACEMENT_RETRACE; higher threshold 1.8 ATR.",
            "observable_inputs": ["bar_disp_atr", "close_location", "disp_sign"],
            "entry_condition": "bar_disp_atr>=1.8 AND close_location aligned with disp_sign",
            "directional_prediction": "WITH_DISPLACEMENT",
            "horizon_bars": 6,
            "min_sample_discovery": 50,
            "success_criteria": "signed ret_atr_H6 effect >=0.12",
            "rejection_criteria": "weak/unstable/sign-flip",
            "execution_cost_model": "BUY ask/SELL bid; TP1.5/SL1.0 ATR; H6 timeout",
            "decision_side": "WITH_DISPLACEMENT",
        },
        {
            "id": "H44_3_VOL_REGIME_TRANSITION",
            "family": "volatility_transition_dynamics",
            "behavior": (
                "When ATR% crosses from below 48-bar p40 into above p60 within 3 bars (vol expansion onset), "
                "the sign of the transition-bar momentum persists over H6."
            ),
            "not_phase42": "Transition event (cross), not static high-vol regime filter (H42_I).",
            "observable_inputs": ["atr_14_pct", "vol_p40", "vol_p60", "mom_3", "transition_flag"],
            "entry_condition": "vol_transition_up AND |mom_3|/ATR>=0.35",
            "directional_prediction": "MOM_SIGN",
            "horizon_bars": 6,
            "min_sample_discovery": 50,
            "success_criteria": "signed effect >=0.12",
            "rejection_criteria": "insufficient n or unstable",
            "execution_cost_model": "BUY ask/SELL bid; TP1.5/SL1.0 ATR; H6 timeout",
            "decision_side": "MOM_SIGN",
        },
        {
            "id": "H44_4_TREND_ACCELERATION",
            "family": "trend_acceleration",
            "behavior": (
                "When short momentum magnitude is increasing (|mom_3| > |mom_3_lag3|) and aligned for "
                "≥4 bars, acceleration continues over H12 more than unconditional."
            ),
            "not_phase42": "Acceleration of momentum, not H1/M5 disagreement (H42_F) or run+wick exhaust (H42_B).",
            "observable_inputs": ["mom_3", "mom_3_lag3", "accel_bars", "run_sign"],
            "entry_condition": "accel_bars>=4 AND |mom_3|/ATR>=0.4",
            "directional_prediction": "ACCEL_SIGN",
            "horizon_bars": 12,
            "min_sample_discovery": 50,
            "success_criteria": "signed effect >=0.12",
            "rejection_criteria": "weak/unstable",
            "execution_cost_model": "BUY ask/SELL bid; TP1.5/SL1.0 ATR; H12 timeout",
            "decision_side": "ACCEL_SIGN",
        },
        {
            "id": "H44_5_TIGHT_SPREAD_PERSISTENCE",
            "family": "spread_conditioned_persistence",
            "behavior": (
                "When the just-completed bar's median bid/ask spread is in the lowest 30% of the day's "
                "spreads so far AND |mom_3|/ATR>=0.35, short-horizon H3 returns continue with momentum "
                "(tight quote → cleaner continuation)."
            ),
            "not_phase42": "Uses spread percentile conditioning, not tick imbalance sign (H42_G).",
            "observable_inputs": ["spread_median_bar", "spread_p30_so_far", "mom_3"],
            "entry_condition": "spread<=p30_so_far AND |mom_3|/ATR>=0.35 AND n_ticks>=20",
            "directional_prediction": "MOM_SIGN",
            "horizon_bars": 3,
            "min_sample_discovery": 50,
            "success_criteria": "signed effect >=0.12",
            "rejection_criteria": "weak/unstable",
            "execution_cost_model": "BUY ask/SELL bid; TP1.5/SL1.0 ATR; H3 timeout",
            "decision_side": "MOM_SIGN",
        },
    ]
    assert len(hyps) <= MAX_HYPOTHESES
    for h in hyps:
        assert not h["id"].startswith(PHASE42_REJECTED_PREFIX)
    return hyps


def freeze_registry(*, stage: str) -> dict[str, Any]:
    hyps = primary_hypotheses()
    body = {
        "recipe_id": RECIPE_ID,
        "stage": stage,
        "frozen": True,
        "optimization_forbidden": True,
        "retired_not_revived": list(RETIRED),
        "phase42_ids_not_revived": True,
        "n_hypotheses": len(hyps),
        "hypotheses": hyps,
        "prediction_horizons_locked": True,
        "statistical_tests_locked": {
            "bonferroni_n": 5,
            "alpha": 0.05,
            "date_block_bootstrap": True,
            "leave_one_date_out": True,
        },
    }
    raw = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    body["registry_sha256"] = hashlib.sha256(raw).hexdigest()
    write_json(f"frozen_hypothesis_registry_{stage}.json", body)
    return body
