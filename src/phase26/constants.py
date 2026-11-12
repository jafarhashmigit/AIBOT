"""Phase 26 constants. Experiment configs predeclared before evaluation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase14.constants import (
    BOOTSTRAP_DRAWS,
    FOLDS,
    MAX_DECISION_TIME,
    PURGE_MINUTES,
    SEED,
    SPREAD_FLOOR_USD,
)
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase26"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase26_orthogonal_feature_outcome_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"
PHASE25_VERDICT = "NO_NEW_EDGE_FOUND"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"
LEGACY_TEST_NAMES = ("xauusd_m5_test.csv",)
MAX_DECISION_TIME_UTC = MAX_DECISION_TIME

FEATURES_PATH = SRC_DIR / "data" / "xauusd_m5_features_utc_corrected.csv"
H1_PATH = SRC_DIR / "data" / "xauusd_h1_mt5.csv"
OOS_PATH = SRC_DIR / "data" / "phase2_oos_predictions.csv"
OUTCOMES_PATH = SRC_DIR / "data" / "m5_side_outcomes.csv"

FOLDS_WF = FOLDS
PURGE_MIN = PURGE_MINUTES
EVAL_SEED = SEED
BOOTSTRAP_N = BOOTSTRAP_DRAWS
SPREAD_FLOOR = SPREAD_FLOOR_USD

# Horizons in M5 bars after entry (entry = next bar open after decision close).
HORIZONS = (1, 2, 3, 4, 6, 8, 12)

# Favorable / adverse thresholds in ATR units of the decision bar (research labels).
FAV_ATR = 0.50
ADV_ATR = 0.50

# Redundancy gate (predeclared): reject candidate if |corr| vs any baseline >= this.
REDUNDANCY_CORR_MAX = 0.92

# Baseline feature columns already in the approved feature store (subset for models).
BASELINE_FEATURE_COLS = (
    "close_to_ema_20",
    "ema_9_20_spread",
    "atr_14_pct",
    "rsi_14",
    "volatility_12",
    "volatility_48",
    "volatility_ratio_12_48",
    "bb_width",
    "candle_range_to_atr",
    "upper_wick_to_range",
    "lower_wick_to_range",
    "return_1",
    "return_6",
    "return_12",
    "momentum_10",
    "corrected_session_new_york",
)

# Predeclared orthogonal candidates (formulas in features.py / research plan).
ORTHOGONAL_CANDIDATES = (
    "rv_6",
    "rv_24",
    "atr_accel_6",
    "range_exp_24",
    "vol_persist_12",
    "er_20",
    "consec_dir",
    "ret_ac1_24",
    "chop_14",
    "dist_prior_high_20_atr",
    "dist_prior_low_20_atr",
    "wick_reject_up_atr",
    "wick_reject_dn_atr",
    "fail_break_up",
    "fail_break_dn",
    "range_compression_6_48",
    "h1_atr_pct",
    "h1_er_10",
    "m5_move_vs_h1_range",
)

# VWAP family skipped: tick_volume is not validated exchange volume.
SKIPPED_FAMILIES = {
    "vwap": "Skipped — tick_volume/real_volume assumptions not validated for true VWAP.",
}

# Predictive experiment configs (predeclared; single pass).
PREDICT_TARGETS = (
    {"id": "fwd_vol_12", "kind": "regression", "horizon": 12},
    {"id": "mfe_buy_12_atr", "kind": "regression", "horizon": 12},
    {"id": "mae_buy_12_atr", "kind": "regression", "horizon": 12},
    {"id": "fwd_ret_buy_6", "kind": "regression", "horizon": 6},
    {"id": "fav_before_adv_buy_12", "kind": "classification", "horizon": 12},
)

VALID_VERDICTS = (
    "NO_INCREMENTAL_INFORMATION",
    "PREDICTIVE_IMPROVEMENT_ONLY",
    "PROMISING_BUT_UNCONFIRMED",
    "CANDIDATE_FOR_FUTURE_SHADOW_TEST",
)

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
OCI_PROVISIONED = False
GITHUB_PUSH = False
AUTONOMOUS_RETRAIN = False


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_hash_snapshot() -> dict[str, str]:
    """Record Phase 16A–25 (+14) protected artifact hashes without modifying them."""
    mapping = dict(PHASE22_PROTECTED_HASHES)
    extra = [
        "src/phase22/constants.py",
        "src/phase22/loop.py",
        "src/phase23/constants.py",
        "src/phase24/constants.py",
        "src/phase25/constants.py",
        "src/phase25/evaluate.py",
        "src/phase14/constants.py",
        "src/phase14/strategy.py",
        "docs/agent/PHASE_25_RESULTS.md",
    ]
    out = {}
    for rel, expected in mapping.items():
        p = PROJECT_ROOT / rel
        out[rel] = {
            "expected_phase22_table": expected,
            "actual": sha256_file(p) if p.exists() else None,
            "match": (sha256_file(p) == expected) if p.exists() else False,
        }
    for rel in extra:
        p = PROJECT_ROOT / rel
        out[rel] = {
            "expected_phase22_table": mapping.get(rel),
            "actual": sha256_file(p) if p.exists() else None,
            "match": None if rel not in mapping else (
                (sha256_file(p) == mapping[rel]) if p.exists() else False
            ),
        }
    return out
