"""Phase 31 forensic diagnosis constants. Research-only; no strategy optimization."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase14.constants import FOLDS, MAX_DECISION_TIME, SEED, SPREAD_FLOOR_USD
from phase16a.constants import FROZEN_CUTS
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES
from label_m5 import (
    EXTRA_COST_PER_SIDE,
    EXTRA_COST_ROUND_TRIP,
    HORIZON_BARS,
    MIN_SPREAD_POINTS,
    POINT_SIZE,
    SL_ATR_MULTIPLE,
    TP_ATR_MULTIPLE,
)

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
PHASE31_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase31"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase31_edge_failure_diagnosis_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "PAUSED_FROZEN_BENCHMARK"
PRODUCTION_FINAL_ACTION = "WAIT"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
MAX_DECISION_TIME_UTC = MAX_DECISION_TIME
HOLDOUT_NAME = "xauusd_m5_test.csv"
EVAL_SEED = SEED

FEATURES_UTC_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"
FEATURES_LEGACY_PATH = DATA_DIR / "xauusd_m5_features.csv"
RAW_M5_PATH = DATA_DIR / "xauusd_m5.csv"
OUTCOMES_PATH = DATA_DIR / "m5_side_outcomes.csv"
OOS_PRED_PATH = DATA_DIR / "phase2_oos_predictions.csv"
PHASE30_SUMMARY = PROJECT_ROOT / "reports" / "phase30" / "phase30_summary.json"

FOLDS_WF = FOLDS
FROZEN_H13C_CUTS = dict(FROZEN_CUTS)

# Cost model documentation (from label_m5 / phase18 — not changed).
KNOWN_COSTS = {
    "spread_floor_points": MIN_SPREAD_POINTS,
    "point_size_usd": POINT_SIZE,
    "spread_floor_usd": MIN_SPREAD_POINTS * POINT_SIZE,
    "extra_cost_per_side_usd": EXTRA_COST_PER_SIDE,
    "extra_cost_round_trip_usd": EXTRA_COST_ROUND_TRIP,
    "tp_atr_multiple": TP_ATR_MULTIPLE,
    "sl_atr_multiple": SL_ATR_MULTIPLE,
    "horizon_bars": HORIZON_BARS,
    "spread_floor_constant_phase14": SPREAD_FLOOR_USD,
}
ASSUMED_COSTS = {
    "note": (
        "MT5 bar spread is minimum-within-bar; floored at 15 points. "
        "Extra $0.05/side models commission+slippage. Bid OHLC assumed."
    )
}
UNAVAILABLE_COSTS = {
    "historical_bid_ask_series": False,
    "actual_fill_slippage_distribution": False,
    "exchange_fee_schedule_time_series": False,
}

COST_SENSITIVITY_MULTS = (0.75, 1.0, 1.25, 1.5, 2.0)
LABEL_SAMPLE_N = 1500
HORIZON_SAMPLE_N = 400
HORIZONS = {"H1": 1, "H2": 2, "H3": 3, "H6": 6, "H12": 12}

VALID_VERDICTS = (
    "NO_CONFIRMED_IMPLEMENTATION_DEFECT",
    "CONFIRMED_DEFECT_REQUIRES_RESEARCH_REASSESSMENT",
    "EXECUTION_MODEL_INSUFFICIENTLY_VALIDATED",
    "STATISTICAL_METHODOLOGY_REQUIRES_REVISION",
    "MULTIPLE_ROOT_CAUSES_FOUND",
    "INCONCLUSIVE",
)

# Phase30 figures to independently verify.
PHASE30_EXPECTED = {
    "h13c": {"n": 226, "mean_r": 0.04856060840719428, "pf": 1.0899746441904932},
    "vol_norm_momentum": {"n": 6611, "mean_r": -0.032667297112387264, "pf": 0.9442313830846566},
    "m15_trend_m5_trigger": {"n": 10031, "mean_r": -0.0494117107544147, "pf": 0.916373257378571},
    "robust_mad_reversion": {"n": 2599, "mean_r": -0.04934843607006664, "pf": 0.9157157657307797},
}

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
GITHUB_PUSH = False
AGENT_SHADOW_WRITES = 0

PROTECTED_HASHES = dict(PHASE22_PROTECTED_HASHES)
