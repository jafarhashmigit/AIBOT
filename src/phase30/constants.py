"""Phase 30 multi-strategy discovery constants. Params predeclared before scoring."""

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
from phase16a.constants import FROZEN_CUTS
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
PHASE30_DIR = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase30"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase30_multi_strategy_discovery_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "PAUSED_FROZEN_BENCHMARK"
PRODUCTION_FINAL_ACTION = "WAIT"
CANDIDATE_ID_H13C = "H13_C_H1_PULLBACK"
H13C_ROLE = "FROZEN_BENCHMARK"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"
MAX_DECISION_TIME_UTC = MAX_DECISION_TIME

FOLDS_WF = FOLDS
PURGE_MIN = PURGE_MINUTES
SPREAD_FLOOR = SPREAD_FLOOR_USD
BOOTSTRAP_N = BOOTSTRAP_DRAWS
EVAL_SEED = SEED
PERMUTATION_N = 500
COST_MULTS = COST_MULTS_CONFIRMATORY
MIN_N_FOLD = MIN_FOLD_N
MIN_N_POOLED = MIN_POOLED_N
MIN_N_DAYS = MIN_DAYS

FROZEN_H13C_CUTS = dict(FROZEN_CUTS)

# PREDECLARED — frozen before scoring. Not tuned on pooled OOS.
STRATEGY_PARAMS: dict[str, dict] = {
    "vol_norm_momentum": {
        "family": "A_trend_persistence",
        "ret_bars": 6,
        "vol_bars": 24,
        "ema_fast": 8,
        "ema_slow": 21,
        "accel_lookback": 3,
        "entry_z": 1.0,
        "vs_phase25": "Not EMA pullback; vol-normalized multi-bar return + EMA slope acceleration.",
    },
    "compression_expansion": {
        "family": "B_volatility_breakout",
        "range_n": 12,
        "compress_ratio": 0.65,
        "expand_ratio": 1.25,
        "break_atr_frac": 0.25,
        "vs_phase25": "Not Donchian retest; compression→expansion transition + close break of prior range.",
    },
    "robust_mad_reversion": {
        "family": "C_standardized_mean_reversion",
        "window": 48,
        "mad_entry": 2.5,
        "atr_pct_min": 0.00025,
        "atr_pct_max": 0.003,
        "vs_phase25": "Median/MAD robust z (not mean/std z+RSI) with different window/threshold.",
    },
    "regression_residual_mr": {
        "family": "D_statistical_residual",
        "trend_n": 40,
        "resid_z_n": 40,
        "entry_z": 1.8,
        "vs_phase25": "OLS residual-to-trend MR; Phase25 had no regression residual family.",
    },
    "wick_exhaustion": {
        "family": "E_candle_path_structure",
        "seq_n": 3,
        "wick_body_min": 1.5,
        "range_atr_min": 0.4,
        "vs_phase25": "Wick rejection sequences + body imbalance; not SMC FVG/BOS.",
    },
    "regime_cond_momentum": {
        "family": "F_vol_regime_conditional",
        "atr_pct_lookback": 96,
        "high_pctile": 0.67,
        "mom_bars": 4,
        "mom_atr_min": 0.35,
        "vs_phase25": "Past ATR-percentile regime gate then momentum; not Phase25 regime_router EMA/MR switch.",
    },
    "london_open_imbalance": {
        "family": "G_time_session",
        "utc_hour_start": 7,
        "utc_hour_end": 10,
        "imb_bars": 6,
        "imb_min": 0.55,
        "vs_phase25": "London UTC imbalance (not NY SELL / Phase4-5). Independently fold-checked.",
    },
    "m15_trend_m5_trigger": {
        "family": "H_multi_timeframe",
        "m15_ema": 8,
        "m5_pullback_atr": 0.3,
        "m5_confirm_bars": 2,
        "vs_phase25": "M15 constructed from closed M5 + M5 trigger; not Phase25 H1+RSI mtf_h1_m5.",
    },
    "body_persistence": {
        "family": "I_path_aware_entry",
        "persist_n": 4,
        "body_range_min": 0.45,
        "vs_phase25": "Executable multi-bar body persistence; not optimized on future MFE/MAE.",
    },
    "momentum_structure_ensemble": {
        "family": "J_simple_ensemble",
        "mom_entry_z": 0.85,
        "wick_body_min": 1.2,
        "vs_phase25": "Agreement of vol-norm momentum + wick structure; Phase25 had no ensemble.",
    },
}

VALID_STATUSES = (
    "REJECTED",
    "WEAK_UNCONFIRMED",
    "PROMISING_BUT_UNCONFIRMED",
    "RESEARCH_CANDIDATE",
)

VALID_VERDICTS = (
    "NO_NEW_EDGE_FOUND",
    "PROMISING_BUT_UNCONFIRMED",
    "RESEARCH_CANDIDATE_FOUND",
)

# Research gates (NOT production gates) — predeclared.
RESEARCH_GATES = {
    "min_pooled_n": MIN_N_POOLED,  # Gate A
    "require_mean_r_gt_0": True,  # Gate B
    "ci_not_strongly_below_zero": True,  # Gate C: ci_high > 0
    "fold_stability": True,  # Gate D: all active folds mean_r > 0
    "cost_1_5x_mean_r_gt_0": True,  # Gate E
    "param_robust_mean_r_gt_0": True,  # Gate F (top only)
    "multiple_testing_aware": True,  # Gate G
}

PERTURB_FRACS = (0.9, 1.1, 0.8, 1.2)  # ±10%, ±20%
TOP_N_FOR_ROBUSTNESS = 3

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
OCI_PROVISIONED = False
GITHUB_PUSH = False
AGENT_SHADOW_WRITES = 0

PROTECTED_HASHES = dict(PHASE22_PROTECTED_HASHES)
