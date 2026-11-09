"""Phase 7 paths and frozen hashes. No threshold search."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase7"

OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"
DECISIONS_PATH = DATA_DIR / "phase7_oos_agent_decisions.csv"
EVALUATION_PATH = DATA_DIR / "phase7_oos_agent_evaluation.csv"

PHASE2_OOS_SHA256 = "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f"
EXPECTED_ROWS = 36468
EXPECTED_PER_SIDE = 18234
RESEARCH_CUTOFF = "2026-09-29 18:50:00"
HOLDOUT_NAME = "xauusd_m5_test.csv"
SEED = 42
N_BOOT = 2000
ESTIMATED_COST_USD = 0.25
FEATURE_VERSION = "m5_utc_corrected_allowlist_v1"
POLICY_ID = "P7_PHASE6_DEFAULT"
RECIPE_ID = "phase7_oos_agent_eval_v1"

OUTCOME_FIELDS = (
    "actual_exit_reason",
    "actual_net_r",
    "actual_net_pnl",
)

DECISION_TIME_PRED_FIELDS = (
    "p_tp_rf",
    "p_sl_rf",
    "p_time_rf",
    "pred_r_rf",
    "pred_r_ridge",
    "pred_r_const",
    "p_tp_prior",
    "p_sl_prior",
    "p_time_prior",
    "p_tp_logreg",
    "p_sl_logreg",
    "p_time_logreg",
    "primary_clf_model_id",
    "primary_reg_model_id",
)
