"""Phase 13 frozen research constants. Pre-registered before scoring."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase13"

RECIPE_ID = "phase13_model_discovery_v1"
SEED = 42
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
HOLDOUT_NAME = "xauusd_m5_test.csv"
RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
MAX_DECISION_TIME = "2026-09-29 17:50:00"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"

FEATURES_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"
OUTCOMES_PATH = DATA_DIR / "m5_side_outcomes.csv"
OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"
H1_PATH = DATA_DIR / "xauusd_h1_mt5.csv"

# Phase 2 walk-forward windows (inclusive rules match Phase 2)
FOLDS = {
    "WF1": {"start": "2026-06-19 03:05:00", "stop": "2026-07-23 11:25:00", "inclusive_stop": False},
    "WF2": {"start": "2026-07-23 11:25:00", "stop": "2026-08-26 13:55:00", "inclusive_stop": False},
    "WF3": {"start": "2026-08-26 13:55:00", "stop": "2026-09-29 17:50:00", "inclusive_stop": True},
}
HORIZON_BARS = 12
BAR_MINUTES = 5
PURGE_MINUTES = HORIZON_BARS * BAR_MINUTES

BREAKOUT_LOOKBACK = 12
BREAKOUT_LOOKBACK_SENSITIVITY = 8
GAP_MIN = 0.05
SPREAD_FLOOR_USD = 0.15
BOOTSTRAP_DRAWS = 2000
FDR_Q = 0.10
MIN_POOLED_TRADES = 100
MIN_FOLD_TRADES = 30
MIN_H1_COVERAGE = 0.95

HYPOTHESIS_IDS = (
    "H13_A_BREAKOUT_FAILURE",
    "H13_B_VOL_EXPANSION_TREND",
    "H13_C_H1_PULLBACK",
    "H13_D_PRED_GAP_MIDVOL",
)

BASELINE_IDS = ("B_WAIT", "B_E1")

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
MODEL_TRAINING_RUNS = 0
STAGE_B_AUTHORIZED = False

# Prior-phase protected hashes (Phase 1–11) live in phase12.validation.
# Phase 12C artifacts must remain unchanged by Phase 13.
PHASE12C_PROTECTED_HASHES = {
    "src/phase12c/gate_adapter.py": "c0b6f20cf8de5b6d3d0096a3627c76a1f134a9890a042cc65bc30c67ad8db1c3",
    "src/phase12c/decision_path.py": "49b7aaa5c3c5d991f3a5cfdbe228ac269d48c8eb0f164c8343fe55de89160e79",
    "src/phase12c/run_phase12c.py": "60d43e7d104bc5b7b8aeebb45bd81f9eff5e3a1d7316a15704a3154e14ded1ad",
    "src/phase12c/constants.py": "bf621d782504ceae1d853901835e1607c67833811a5fa467a9da2891b4f8f156",
    "docs/agent/PHASE_12C_FORWARD_COMPATIBILITY.md": "95962f672e506b2d7836362c4bb797bd5e59dcb7cc25a13a040125c761dc9dab",
    "docs/agent/PHASE_12C_MODEL_READINESS.md": "fdb3acaa7d90251077567568a028a19d6267c89c0cb09cb916ec00684f6882e0",
    "reports/phase12c/phase12c_summary.json": "757e0ff28f55857dffa9b31e8db53f8333870da131646c9b356e1e0a5f5a8c45",
    "reports/phase12c/model_readiness.json": "4687d751955af45ba27a459b7358e4ce535c470c033ba45ee897e6487cc4082b",
}
