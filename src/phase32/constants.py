"""Phase 32 independent validation constants. Research-only."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase32"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase32_independent_data_execution_validation_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "PAUSED_FROZEN_BENCHMARK"
PRODUCTION_FINAL_ACTION = "WAIT"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"
EVAL_SEED = 42

RAW_M5_PATH = DATA_DIR / "xauusd_m5.csv"
FEATURES_PATH = DATA_DIR / "xauusd_m5_features.csv"
FEATURES_UTC_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"
LABELED_PATH = DATA_DIR / "xauusd_m5_labeled.csv"
OUTCOMES_PATH = DATA_DIR / "m5_side_outcomes.csv"
PHASE30_SUMMARY = PROJECT_ROOT / "reports" / "phase30" / "phase30_summary.json"
PHASE31_FINAL = PROJECT_ROOT / "reports" / "phase31" / "final_verdict.json"

# Frozen cost/label contract (duplicated locally — not imported from label generators).
BAR_MINUTES = 5
HORIZON_BARS = 12
TP_ATR_MULTIPLE = 1.5
SL_ATR_MULTIPLE = 1.0
POINT_SIZE = 0.01
MIN_SPREAD_POINTS = 15
EXTRA_COST_PER_SIDE = 0.05
SERVER_TZ = "Europe/Athens"

SESSIONS = {
    "asia": ("Asia/Tokyo", 9, 18),
    "london": ("Europe/London", 8, 17),
    "new_york": ("America/New_York", 8, 17),
}
SESSION_IDS = {"off_hours": 0, "asia": 1, "london": 2, "london_ny_overlap": 3, "new_york": 4}

FEATURE_TOL_ABS = 1e-10
FEATURE_TOL_REL = 1e-9
LABEL_TOL_ABS = 1e-8

EXPECTED_RAW_ROWS = 50000
EXPECTED_FEATURE_ROWS = 49951
EXPECTED_UTC_FEATURE_ROWS = 42450
EXPECTED_LABELED_ROWS = 47683
EXPECTED_GAPS_FULL = 188

VALID_VERDICTS = (
    "INDEPENDENT_VALIDATION_PASSED",
    "FEATURE_RECOMPUTATION_MISMATCH",
    "LABEL_RECONSTRUCTION_MISMATCH",
    "TRADE_ACCOUNTING_MISMATCH",
    "EXECUTION_REALISM_UNVERIFIED",
    "MULTIPLE_VALIDATION_FAILURES",
    "INCONCLUSIVE",
)

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
GITHUB_PUSH = False
AGENT_SHADOW_WRITES = 0
PROTECTED_HASHES = dict(PHASE22_PROTECTED_HASHES)
