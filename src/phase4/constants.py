"""Phase 4 constants. Standalone catalogue, declared before outer scoring."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase4"
UTC_FEATURES_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"
HISTORY_PROBE_PATH = PROJECT_ROOT / "reports" / "phase1" / "m5_history_depth_probe.json"
SIDE_OUTCOMES_VERIFY_PATH = PROJECT_ROOT / "reports" / "phase1" / "side_outcomes_verification.json"

SEED = 42
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
RESEARCH_CUTOFF = "2026-09-29 18:50:00"
VALIDATION_END = "2026-09-29 17:50:00"
HOLDOUT_NAME = "xauusd_m5_test.csv"
RECIPE_ID = "phase4_regime_edge_v1"
FEATURE_VERSION = "m5_utc_corrected_allowlist_v1"

# Decision-time columns joined from the UTC-corrected feature file.
UTC_KEEP = (
    "time",
    "atr_14_pct",
    "ema_9_20_spread",
    "volatility_ratio_12_48",
    "minutes_since_prev_bar",
    "corrected_hour_utc",
    "corrected_weekday_utc",
    "corrected_session_asia",
    "corrected_session_london",
    "corrected_session_new_york",
    "corrected_session_london_ny_overlap",
    "corrected_session_id",
)

SESSION_NAMES = {
    0: "off_hours",
    1: "asia",
    2: "london",
    3: "london_ny_overlap",
    4: "new_york",
}

HOUR_BUCKETS = (
    ("utc_00_07", range(0, 8)),
    ("utc_08_12", range(8, 13)),
    ("utc_13_16", range(13, 17)),
    ("utc_17_23", range(17, 24)),
)

WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}

SIDES = ("BUY", "SELL")
MIN_SLICE_N = 50
MIN_SLICE_N_PER_FOLD = 50
FDR_Q = 0.10
SPREAD_STRESS = (1.5, 2.0)
SPREAD_FLOOR_USD = 0.15

# Confirmatory family: unconditional take-this-side in a predeclared regime.
# Not E1, not meta, not threshold search. Finite list only.
REGIME_FAMILIES = (
    "session",
    "hour_bucket",
    "weekday",
    "atr_tercile",
    "trend_ema920",
)

GATE = {
    "min_pooled": 100,
    "min_per_fold": 50,
    "require_both_folds_positive": True,
    "ci_low_must_exceed": 0.0,
    "spread_1_5_mean_r_gt_0": True,
    "fdr_q": FDR_Q,
    "note": (
        "A slice is a potentially credible conditional edge only if it was "
        "predeclared, uses outer OOS timestamps, mean R > 0 after costs in "
        "both outer folds, pooled n >= 100 and n >= 50 per fold, day-cluster "
        "CI lower bound > 0, BH-FDR q=0.10 among the confirmatory family, "
        "and 1.5x spread-floor stress still has mean R > 0. "
        "Picking the best of many slices after seeing outer results is forbidden."
    ),
}

PHASE2_OOS_SHA256 = "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f"
