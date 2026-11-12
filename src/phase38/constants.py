"""Phase 38 constants — canonical historical data engine. No strategy research."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase38"
DATA_ROOT = SRC_DIR / "data" / "phase38"
RAW_M5_DIR = DATA_ROOT / "mt5" / "raw" / "m5"
RAW_TICKS_DIR = DATA_ROOT / "mt5" / "raw" / "ticks"
CANONICAL_DIR = DATA_ROOT / "mt5" / "canonical"
MANIFESTS_DIR = DATA_ROOT / "manifests"
REJECTED_DIR = DATA_ROOT / "rejected"
STATE_DIR = DATA_ROOT / "state"

PHASE37_DATA = SRC_DIR / "data" / "phase37" / "mt5"
PHASE37_REPORTS = PROJECT_ROOT / "reports" / "phase37"
PHASE34_TICKS = SRC_DIR / "data" / "phase34" / "ticks_decoded"

RECIPE_ID = "phase38_canonical_historical_data_engine_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"
EXPECTED_DIGITS = 2
EXPECTED_POINT = 0.01
EXPECTED_MT5_BUILD = 6314
EXPECTED_PACKAGE_VERSION = "5.0.6231"
SOURCE_SERVER_LABEL = "MetaQuotes-Demo"

COVERAGE_START = datetime(2025, 7, 1, 0, 0, tzinfo=timezone.utc)
COVERAGE_END = datetime(2026, 9, 29, 18, 50, tzinfo=timezone.utc)
RESEARCH_CUTOFF_UTC = "2026-09-29 18:50:00"

MAX_WALL_SECONDS = 600
MAX_ACQUIRE_DATES = 10
INIT_TIMEOUT_MS = 60000
TICK_SAMPLE_HOURS = 3  # liquid-hour tick window per date (bounded)
TICK_SAMPLE_START_HOUR_UTC = 12

# Representative acquisition dates (Mon–Fri preference; distributed across coverage)
REPRESENTATIVE_DATES = [
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

# Monthly coverage probe months (first weekday-ish checkpoints)
COVERAGE_PROBE_DAYS = [
    "2025-07-01",
    "2025-07-15",
    "2025-08-01",
    "2025-09-01",
    "2025-10-01",
    "2025-11-03",
    "2025-12-01",
    "2026-01-05",
    "2026-02-02",
    "2026-02-16",
    "2026-03-02",
    "2026-04-01",
    "2026-05-04",
    "2026-06-02",
    "2026-07-01",
    "2026-08-03",
    "2026-09-01",
    "2026-09-15",
    "2026-09-28",
]

PHASE38_PROHIBITED_MT5_API = frozenset(
    {
        "order_send",
        "order_check",
        "order_calc_margin",
        "order_calc_profit",
        "positions_get",
        "positions_total",
        "orders_get",
        "orders_total",
        "history_orders_get",
        "history_deals_get",
        "buy",
        "sell",
        "Close",
        "symbol_select",
        "order_send_async",
    }
)

BROKER_ORDERS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
HOLDOUT_ACCESSES = 0
GIT_COMMIT = False
GIT_PUSH = False
MT5_CONNECTIONS = 0
