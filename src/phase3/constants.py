"""Phase 3 constants. Standalone: does not import pandas or Phase 1/2 modules."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
PHASE3_DIR = SRC_DIR / "phase3"
MODELS_DIR = SRC_DIR / "models" / "phase3"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase3"
OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"
JOURNAL_PATH = DATA_DIR / "phase3_decision_journal.csv"
ACTIONS_PATH = DATA_DIR / "phase3_policy_actions.csv"

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
RESEARCH_CUTOFF = "2026-09-29 18:50:00"
VALIDATION_END = "2026-09-29 17:50:00"
EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]

SEED = 42
PURGE_BARS = 12
HORIZON_BARS = 12
BAR_MINUTES = 5
SIDES = ("BUY", "SELL")
OUTCOME_CLASSES = ("TP", "SL", "TIME")
ACTIONS = ("BUY", "SELL", "WAIT")

FEATURE_VERSION = "phase3_decision_allowlist_v1"
RECIPE_ID = "phase3_decision_layer_v1"
POLICY_VERSION = "phase3_p3_conservative_ev_v1"
LABEL_VERSION = "m5_side_outcomes_exit_reason_net_r_v1"
PRIMARY_PRED_SOURCE = "phase2_rf_oos"

PHASE2_OOS_SHA256 = "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f"

PHASE2_SOURCE_SHA256_16 = {
    "src/phase2/constants.py": "9cc88e29c9ab89e3",
    "src/phase2/evaluate.py": "4a2a42e1863338b8",
    "src/phase2/train_oos.py": "5aac4b809e1d1afc",
    "src/phase2/feature_audit.py": "ad823fc7e0b5be0d",
    "src/phase2/dataset.py": "171d31c4557ffc6b",
    "src/phase2/splits.py": "fcbef70fb211def7",
    "src/phase2/run_phase2.py": "ff7ef8535f1e4e69",
    "src/phase2/write_registry.py": "a114e330a3ac6dd7",
    "docs/agent/PHASE_2_INPUT_AUDIT.md": "d246e81570c5833b",
    "docs/agent/PHASE_2_WALK_FORWARD_DESIGN.md": "7f2aff231875d43d",
    "docs/agent/PHASE_2_FEATURE_LEAKAGE_REPORT.md": "6010c5e47b832864",
    "docs/agent/PHASE_2_MODEL_RESULTS.md": "7ef0d6039fa4d9d5",
    "docs/agent/PHASE_2_LIMITATIONS.md": "3d9505b4aa5989fd",
}

NESTED_FOLDS = (
    {
        "nested_id": "N1",
        "inner_phase2_folds": ("WF1",),
        "outer_phase2_fold": "WF2",
        "outer_start": EXPECTED_WF_WINDOWS[1][0],
        "outer_stop": EXPECTED_WF_WINDOWS[1][1],
        "inclusive_stop": False,
    },
    {
        "nested_id": "N2",
        "inner_phase2_folds": ("WF1", "WF2"),
        "outer_phase2_fold": "WF3",
        "outer_start": EXPECTED_WF_WINDOWS[2][0],
        "outer_stop": EXPECTED_WF_WINDOWS[2][1],
        "inclusive_stop": True,
    },
)

DECISION_FEATURE_ALLOWLIST = (
    "p_tp_rf_BUY",
    "p_sl_rf_BUY",
    "p_time_rf_BUY",
    "p_tp_rf_SELL",
    "p_sl_rf_SELL",
    "p_time_rf_SELL",
    "pred_r_rf_BUY",
    "pred_r_rf_SELL",
    "pred_r_ridge_BUY",
    "pred_r_ridge_SELL",
    "pred_r_rf_diff",
    "p_tp_rf_diff",
    "p_tp_minus_sl_rf_BUY",
    "p_tp_minus_sl_rf_SELL",
)

FORBIDDEN_DECISION_COLUMNS = (
    "actual_exit_reason",
    "actual_net_r",
    "actual_net_pnl",
    "actual_exit_reason_BUY",
    "actual_exit_reason_SELL",
    "actual_net_r_BUY",
    "actual_net_r_SELL",
    "actual_net_pnl_BUY",
    "actual_net_pnl_SELL",
    "exit_time",
    "exit_price",
    "exit_reason",
    "gross_pnl",
    "net_pnl",
    "net_r",
    "costs",
    "entry_fill",
    "stop_price",
    "target_price",
)

C_TAU_CANDIDATES = (0.05, 0.10, 0.20)
D_TAU_CANDIDATES = (0.00, 0.10, 0.20)
EV_TAU_CANDIDATES = (0.00, 0.05, 0.10)
CONS_TAU_CANDIDATES = (0.00, 0.05)
META_TAU_CANDIDATES = (0.00, 0.05)

MIN_INNER_TRADES = 50
UNCERTAINTY_K = 1.0
CONS_MIN_GAP = 0.02
DEFAULT_MIN_GAP = 0.0
PERTURBATIONS = (-0.02, 0.02)
SPREAD_STRESS_MULTIPLIERS = (1.5, 2.0)
SPREAD_FLOOR_USD = 15 * 0.01
ROUND_TRIP_EXTRA_USD = 0.10

THRESHOLD_SELECTION_RULE = {
    "id": "inner_positive_then_most_conservative",
    "declared_before_outer": True,
    "rule": (
        "On the inner window only: keep candidate thresholds with at least "
        "MIN_INNER_TRADES executed trades and strictly positive mean trade R. "
        "If any remain, choose the highest threshold (most conservative). "
        "If none remain, freeze Always-WAIT for that nested fold. "
        "Outer evaluation is not used for this choice."
    ),
}

FROZEN_POLICY_ID = "P3_CONSERVATIVE_EV"
FROZEN_POLICY = {
    "id": FROZEN_POLICY_ID,
    "version": POLICY_VERSION,
    "declared_before_outer": True,
    "description": (
        "At each timestamp, EV_side = p_tp_rf*E[R|TP,side] + p_sl_rf*E[R|SL,side] "
        "+ p_time_rf*E[R|TIME,side], with class-conditional means estimated on the "
        "inner window only. Conservative EV = EV - 1.0 * inner MAE(EV, actual R) "
        "per side. BUY if cons_EV_BUY > cons_EV_SELL and cons_EV_BUY > tau and "
        "|cons_EV_BUY-cons_EV_SELL| >= 0.02; SELL symmetrically; else WAIT. "
        "tau selected on the inner window from {0.00, 0.05} by "
        "inner_positive_then_most_conservative."
    ),
}

LOGREG_PARAMS = {
    "max_iter": 1000,
    "C": 1.0,
    "class_weight": "balanced",
    "solver": "lbfgs",
    "random_state": SEED,
}
RIDGE_PARAMS = {"alpha": 1.0}

META_RF_USED = False
META_RF_REASON = (
    "Phase 2 RF expected-R correlation was ~0.03, indistinguishable from a "
    "constant mean. No baseline result in this phase is allowed to justify an "
    "RF meta-model after seeing outer outcomes, so RF is omitted a priori."
)

HOLDOUT_NAME = "xauusd_m5_test.csv"
