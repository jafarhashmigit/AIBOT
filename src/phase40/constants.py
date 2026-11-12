"""Phase 40 constants — targeted historical coverage completion. No strategy eval."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase40"
DATA_ROOT = SRC_DIR / "data" / "phase40"
RAW_M5 = DATA_ROOT / "mt5" / "raw" / "m5"
RAW_H1 = DATA_ROOT / "mt5" / "raw" / "h1"
RAW_TICKS = DATA_ROOT / "mt5" / "raw" / "ticks"
CANONICAL = DATA_ROOT / "mt5" / "canonical"
MANIFESTS = DATA_ROOT / "manifests"
STATE_DIR = DATA_ROOT / "state"
REJECTED = DATA_ROOT / "rejected"

PHASE38_ROOT = SRC_DIR / "data" / "phase38"
PHASE38_RAW_M5 = PHASE38_ROOT / "mt5" / "raw" / "m5"
PHASE38_RAW_TICKS = PHASE38_ROOT / "mt5" / "raw" / "ticks"
PHASE38_MANIFESTS = PHASE38_ROOT / "manifests"
PHASE39_REPORTS = PROJECT_ROOT / "reports" / "phase39"
PHASE37_REPORTS = PROJECT_ROOT / "reports" / "phase37"

RECIPE_ID = "phase40_targeted_historical_coverage_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"
SOURCE_SERVER_LABEL = "MetaQuotes-Demo"
INIT_TIMEOUT_MS = 60000
MAX_WALL_SECONDS = 600
HORIZON_BARS = 12
H1_WARMUP_BARS = 30  # before evaluation date
TICK_HOURS = list(range(24))

TARGET_DATES = [
    "2025-07-01",
    "2025-08-15",
    "2025-10-01",
    "2025-12-01",
    "2026-01-15",
    "2026-02-16",
    "2026-04-15",
    "2026-06-02",
    "2026-08-03",
    "2026-09-15",
]

# Future additional-date candidates (NOT downloaded in Phase40)
ADDITIONAL_DATE_CANDIDATES = [
    "2025-07-15",
    "2025-09-02",
    "2025-11-03",
    "2026-03-02",
    "2026-05-04",
    "2026-07-01",
    "2026-09-01",
    "2026-09-28",
]

BROKER_ORDERS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
HOLDOUT_ACCESSES = 0
GIT_COMMIT = False
GIT_PUSH = False
MT5_CONNECTIONS = 0

PHASE40_PROHIBITED = frozenset(
    {
        "order_send",
        "order_check",
        "positions_get",
        "orders_get",
        "buy",
        "sell",
        "Close",
        "symbol_select",
    }
)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
