"""Phase 24 constants. Does not modify Phase 16A–23."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase24"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DATA_DIR = SRC_DIR / "data"

RECIPE_ID = "phase24_provider_arm64_qualification_v1"
FINAL_DECISION = "PROVIDER_BLOCKED"

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF  # 2026-09-29 18:50:00
HOLDOUT_NAME = "xauusd_m5_test.csv"
MT5_FEATURES_PATH = DATA_DIR / "xauusd_m5_features_utc_corrected.csv"

# Approved parity window inside training/validation period (before holdout).
PARITY_WINDOW_START = "2026-02-16 00:00:00"
PARITY_WINDOW_END = "2026-02-17 23:55:00"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
OCI_PROVISIONED = False
ACCOUNTS_CREATED = False
GITHUB_PUSH = False

# Runtime deps from requirements.txt (pins).
PINNED_RUNTIME = {
    "numpy": "2.5.4",
    "pandas": "3.1.1",
    "scikit-learn": "1.9.1",
    "scipy": "1.18.1",
    "joblib": "1.6.0",
    "tzdata": "2026.6",
    "MetaTrader5": "5.0.6231",
}

WINDOWS_ONLY_RUNTIME = ("MetaTrader5",)

# Reuse Phase 22 protected hash map for integrity reporting (read-only).
from phase22.constants import PROTECTED_HASHES  # noqa: E402
