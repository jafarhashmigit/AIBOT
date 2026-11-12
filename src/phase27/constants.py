"""Phase 27 constants. Regime boundaries method predeclared before evaluation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase14.constants import (
    BOOTSTRAP_DRAWS,
    FOLDS,
    MAX_DECISION_TIME,
    PRIMARY_PULLBACK_Q_HIGH,
    PRIMARY_PULLBACK_Q_LOW,
    PURGE_MINUTES,
    SEED,
    SPREAD_FLOOR_USD,
)
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES
from phase26.constants import BASELINE_FEATURE_COLS

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase27"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase27_volatility_aware_decision_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"
PHASE25_VERDICT = "NO_NEW_EDGE_FOUND"
PHASE26_VERDICT = "PROMISING_BUT_UNCONFIRMED"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"
MAX_DECISION_TIME_UTC = MAX_DECISION_TIME
FOLDS_WF = FOLDS
PURGE_MIN = PURGE_MINUTES
EVAL_SEED = SEED
BOOTSTRAP_N = BOOTSTRAP_DRAWS
SPREAD_FLOOR = SPREAD_FLOOR_USD

# Frozen H13_C cuts — must match Phase 14 (unchanged).
H13C_Q_LOW = PRIMARY_PULLBACK_Q_LOW
H13C_Q_HIGH = PRIMARY_PULLBACK_Q_HIGH

# Phase 26 accepted orthogonal features (frozen list from Phase 26 results).
PHASE26_ACCEPTED = (
    "rv_6",
    "rv_24",
    "atr_accel_6",
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

BASELINE_COLS = BASELINE_FEATURE_COLS
VOL_FEATURE_SET = tuple(list(BASELINE_COLS) + list(PHASE26_ACCEPTED))

# Predeclared regime method: fold-train tertiles of *predicted* fwd_vol_12.
REGIME_METHOD = "train_predicted_vol_tertiles"
REGIME_LABELS = ("low", "medium", "high")

# Minimum trades for a subgroup to be considered confirmatory (else unconfirmed).
MIN_SUBGROUP_N = 30
MIN_FOLD_POLICY_N = 15

# Primary hypotheses for Bonferroni (predeclared count = 6).
PRIMARY_HYPOTHESES = (
    "skip_high_vs_baseline_mean_r",
    "skip_low_vs_baseline_mean_r",
    "buy_high_vs_buy_low_mean_r",
    "sell_high_vs_sell_low_mean_r",
    "pred_vol_corr_net_r",
    "fwd_vol_mae_improves_all_folds",
)
BONFERRONI_ALPHA = 0.05

VALID_VERDICTS = (
    "NO_DECISION_VALUE",
    "VOLATILITY_PREDICTION_ONLY",
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


def protected_hash_snapshot() -> dict:
    out = {}
    for rel, expected in PHASE22_PROTECTED_HASHES.items():
        p = PROJECT_ROOT / rel
        actual = sha256_file(p) if p.exists() else None
        out[rel] = {
            "expected": expected,
            "actual": actual,
            "match": actual == expected if actual is not None else False,
        }
    for rel in (
        "src/phase14/constants.py",
        "src/phase14/strategy.py",
        "src/phase25/constants.py",
        "src/phase26/constants.py",
        "docs/agent/PHASE_26_RESULTS.md",
    ):
        p = PROJECT_ROOT / rel
        out[rel] = {
            "expected": None,
            "actual": sha256_file(p) if p.exists() else None,
            "match": None,
        }
    return out
