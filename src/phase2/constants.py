"""Phase 2 constants. New file only. Does not change Phase 1 rules."""

from __future__ import annotations

from pathlib import Path

from evaluation.constants import (
    DATA_DIR,
    DEFAULT_SEED,
    EXPECTED_WF_WINDOWS,
    PROJECT_ROOT,
    RESEARCH_CUTOFF,
    SRC_DIR,
    TIME_FORMAT,
    VALIDATION_END,
)
from label_m5 import HORIZON_BARS, PURGE_BARS

PHASE2_DIR = SRC_DIR / "phase2"
MODELS_DIR = SRC_DIR / "models" / "phase2"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase2"
OUTCOMES_PATH = DATA_DIR / "m5_side_outcomes.csv"
UTC_FEATURES_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"
OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"

OUTCOME_CLASSES = ("TP", "SL", "TIME")
SIDES = ("BUY", "SELL")
SEED = DEFAULT_SEED
PURGE_BARS = PURGE_BARS
HORIZON_BARS = HORIZON_BARS

# Identifiers and join keys — not model features.
ID_COLUMNS = ("decision_time", "side")

# Fields that exist only after the trade window. Never used as inputs.
OUTCOME_COLUMNS = (
    "entry_time",
    "entry_fill",
    "stop_price",
    "target_price",
    "exit_time",
    "exit_reason",
    "gross_pnl",
    "costs",
    "net_pnl",
    "initial_risk",
    "net_r",
    "eligible",
    "incomplete_window",
    "crosses_gap",
)

# Decision-time allowlist. Original hour_utc / weekday / session_* are excluded
# because they treat Athens server time as UTC (Phase 1 clock audit).
# Replaced by corrected_* columns from xauusd_m5_features_utc_corrected.csv.
FEATURE_ALLOWLIST = (
    "close_to_ema_9",
    "close_to_ema_50",
    "ema_9_20_spread",
    "ema_20_50_spread",
    "rsi_14",
    "bb_percent_b",
    "bb_width",
    "atr_14_pct",
    "volatility_12",
    "volatility_48",
    "volatility_ratio_12_48",
    "candle_body_abs_to_range",
    "upper_wick_to_range",
    "lower_wick_to_range",
    "candle_range_to_atr",
    "log_return_1",
    "return_3",
    "return_6",
    "return_12",
    "roc_20",
    "log_tick_volume",
    "tick_volume_change",
    "tick_volume_ratio_20",
    "minutes_since_prev_bar",
    "corrected_hour_utc",
    "corrected_weekday_utc",
    "corrected_session_asia",
    "corrected_session_london",
    "corrected_session_new_york",
    "corrected_session_london_ny_overlap",
)

EXCLUDED_CLOCK_COLUMNS = (
    "hour_utc",
    "weekday",
    "session_asia",
    "session_london",
    "session_new_york",
    "session_london_ny_overlap",
    "session_id",
    "hour",
    "minute",
    "time_utc",
    "corrected_time_utc",
    "corrected_session_id",
)

# Frozen estimator configs. Not tuned on evaluation folds.
LOGREG_PARAMS = {
    "max_iter": 1000,
    "C": 1.0,
    "class_weight": "balanced",
    "solver": "lbfgs",
    "random_state": SEED,
}
RF_CLF_PARAMS = {
    "n_estimators": 200,
    "max_depth": 8,
    "min_samples_leaf": 50,
    "max_features": "sqrt",
    "max_samples": 0.5,
    "bootstrap": True,
    "class_weight": "balanced",
    "random_state": SEED,
    "n_jobs": -1,
}
RIDGE_PARAMS = {"alpha": 1.0}
RF_REG_PARAMS = {
    "n_estimators": 200,
    "max_depth": 8,
    "min_samples_leaf": 50,
    "max_features": "sqrt",
    "max_samples": 0.5,
    "bootstrap": True,
    "random_state": SEED,
    "n_jobs": -1,
}

# Pre-declared experimental readout (frozen before OOS numbers are seen).
# Not a live policy. Not optimized on OOS.
SELECTION_RULE = {
    "id": "E1_max_predicted_r_positive",
    "declared_before_oos": True,
    "description": (
        "At each evaluation timestamp, take the side with the larger predicted "
        "expected net R if that value is strictly greater than 0; otherwise WAIT. "
        "At most one side per timestamp. Realized P&L is the stored side-outcome "
        "net_pnl / net_r (already includes the approved cost model)."
    ),
}

FEATURE_VERSION = "m5_utc_corrected_allowlist_v1"
LABEL_VERSION = "m5_side_outcomes_exit_reason_net_r_v1"
RECIPE_ID = "phase2_primary_outcome_v1"
