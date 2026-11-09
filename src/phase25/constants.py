"""Phase 25 strategy discovery constants. Params predeclared before evaluation."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase14.constants import (
    BOOTSTRAP_DRAWS,
    COST_MULTS_CONFIRMATORY,
    FOLDS,
    MAX_DECISION_TIME,
    MIN_DAYS,
    MIN_FOLD_N,
    MIN_POOLED_N,
    PURGE_MINUTES,
    SEED,
    SPREAD_FLOOR_USD,
)

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase25"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase25_strategy_discovery_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"
CANDIDATE_ID_H13C = "H13_C_H1_PULLBACK"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"
MAX_DECISION_TIME_UTC = MAX_DECISION_TIME

FEATURES_PATH = SRC_DIR / "data" / "xauusd_m5_features_utc_corrected.csv"
OUTCOMES_PATH = SRC_DIR / "data" / "m5_side_outcomes.csv"
OOS_PATH = SRC_DIR / "data" / "phase2_oos_predictions.csv"
H1_PATH = SRC_DIR / "data" / "xauusd_h1_mt5.csv"

FOLDS_WF = FOLDS
PURGE_MIN = PURGE_MINUTES
SPREAD_FLOOR = SPREAD_FLOOR_USD
BOOTSTRAP_N = BOOTSTRAP_DRAWS
EVAL_SEED = SEED
COST_MULTS = COST_MULTS_CONFIRMATORY
MIN_N_FOLD = MIN_FOLD_N
MIN_N_POOLED = MIN_POOLED_N
MIN_N_DAYS = MIN_DAYS

FEATURE_KEEP = (
    "time",
    "open",
    "high",
    "low",
    "close",
    "close_to_ema_20",
    "ema_9_20_spread",
    "atr_14_pct",
    "rsi_14",
    "volatility_12",
    "volatility_48",
    "volatility_ratio_12_48",
    "corrected_session_new_york",
    "corrected_session_london",
    "corrected_session_asia",
)

# PREDECLARED — frozen before scoring. Not tuned post-hoc.
STRATEGY_PARAMS = {
    "mean_reversion": {
        "z_window": 40,
        "z_entry": 1.75,
        "rsi_buy_max": 35.0,
        "rsi_sell_min": 65.0,
        "atr_pct_min": 0.0003,
        "atr_pct_max": 0.0025,
        "vol_ratio_max": 1.35,
    },
    "breakout_retest": {
        "donchian_n": 20,
        "min_break_atr_pct": 0.15,
        "retest_tol_atr_pct": 0.35,
        "false_break_lookback": 3,
    },
    "smc_liquidity": {
        "swing_lookback": 3,
        "fvg_min_atr_frac": 0.15,
        "require_bos": True,
    },
    "regime_router": {
        "ema_spread_trend": 0.00035,
        "atr_pct_highvol": 0.0018,
        "trend_pullback_z": 0.75,
    },
    "mtf_h1_m5": {
        "m5_rsi_buy_max": 45.0,
        "m5_rsi_sell_min": 55.0,
        "ema_spread_confirm": 0.0,
        "require_h1_align": True,
    },
}

VALID_STATUSES = (
    "REJECTED",
    "INCONCLUSIVE",
    "PROMISING_BUT_UNCONFIRMED",
    "CANDIDATE_FOR_FUTURE_SHADOW_TEST",
)

CANDIDATE_GATES = {
    "pooled_mean_r_gt_0": True,
    "ci_low_gt_0": True,
    "all_active_folds_mean_r_gt_0": True,
    "cost_1_5x_mean_r_gt_0": True,
    "min_pooled_n": MIN_N_POOLED,
    "min_days": MIN_N_DAYS,
    "beats_h13c_pooled_mean_r": True,
}

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
OCI_PROVISIONED = False
GITHUB_PUSH = False
AUTONOMOUS_RETRAIN = False

REPOS_AUDITED = (
    "https://github.com/0xagarg/xau-ai-trading-bot",
    "https://github.com/MooreSi/forex-gold",
    "https://github.com/Kiran-Kumbar/XAU-USD-Signal-Bot",
    "https://github.com/n30dyn4m1c/gold-pro-scalper",
    "https://github.com/sankett04/XAUUSD-signal-system",
)
