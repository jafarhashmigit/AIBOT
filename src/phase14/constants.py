"""Phase 14 frozen validation constants. Pre-declared before scoring."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase14"

RECIPE_ID = "phase14_h13c_validation_v1"
SEED = 42
HOLDOUT_NAME = "xauusd_m5_test.csv"
RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
MAX_DECISION_TIME = "2026-09-29 17:50:00"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE_ID = "H13_C_H1_PULLBACK"

FEATURES_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"
OUTCOMES_PATH = DATA_DIR / "m5_side_outcomes.csv"
OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"
H1_PATH = DATA_DIR / "xauusd_h1_mt5.csv"

FOLDS = {
    "WF1": {"start": "2026-06-19 03:05:00", "stop": "2026-07-23 11:25:00", "inclusive_stop": False},
    "WF2": {"start": "2026-07-23 11:25:00", "stop": "2026-08-26 13:55:00", "inclusive_stop": False},
    "WF3": {"start": "2026-08-26 13:55:00", "stop": "2026-09-29 17:50:00", "inclusive_stop": True},
}
PURGE_MINUTES = 60
SPREAD_FLOOR_USD = 0.15
BOOTSTRAP_DRAWS = 2000
PRIMARY_PULLBACK_Q_LOW = 25
PRIMARY_PULLBACK_Q_HIGH = 75
MIN_FOLD_N = 30
MIN_POOLED_N = 100
MIN_DAYS = 40
MIN_H1_COVERAGE = 0.95
PHASE13_REPORTED_N = 226
PHASE13_REPORTED_MEAN_R = 0.04856060840719428

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
STAGE_B_AUTHORIZED = False

# Cost stress confirmatory multipliers
COST_MULTS_CONFIRMATORY = (1.0, 1.25, 1.5, 2.0)

# Exploratory sensitivity grid (fixed; not searched for a winner)
SENS_PULLBACK_Q = (20, 25, 30)
SENS_H1_STRICT = (True, False)  # True: close > ema; False: close >= ema
SENS_ENTRY_DELAY = (0, 1)
SENS_SLIPPAGE_USD = (0.0, 0.05)

PHASE13_PROTECTED_HASHES = {
    "src/phase13/hypotheses.py": "11e0e98772859de88e15285db89c2d0d60759af9df9e03c52abfcbdda1b7f7fd",
    "src/phase13/evaluate.py": "6ec862b5c3fb030ed8c9921df8b60b1abaddd485c22be6bc980d4d748892c0ca",
    "src/phase13/data_loader.py": "be2eaf4a8b0ece376d0f4c12943e1d03c13627719417c914946f485fd5c7689a",
    "src/phase13/h1_context.py": "c89163791f1dbebf54223799c792a37a490f293efb7436c307057b2fdd936d10",
    "src/phase13/run_phase13.py": "e9dbfdbc11ed2e627fabf30281e2da060742ae4ac0ddd96cf7f5f269735fda84",
    "docs/agent/PHASE_13_RESULTS.md": "4a9878673a347153d2834837318a74e541c33fb34cd73af40e8077248dfb2f72",
    "docs/agent/PHASE_13_RESEARCH_PLAN.md": "127e58a016e6ebbcc161b4f4a425314824bbc0fc9cb16435fad283ad5a0b0cd6",
    "reports/phase13/phase13_summary.json": "7a021946daeb16b7d998140ce17b593e76230915689fd6d0282f15a5fbfba00b",
    "reports/phase13/candidate_comparison.json": "e5741de7ed71be084a6c22e581f4c5ff87512b7b4f78d4abee924d04f74e3488",
    "reports/phase13/economic_validation.json": "de7440823c010479b419f881a2b4025745ec2de3a73b0a288a6a82daf367901f",
}
