"""Phase 37 constants — MT5 historical data qualification only. No strategy eval."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase37"
DATA_ROOT = SRC_DIR / "data" / "phase37" / "mt5"
BARS_DIR = DATA_ROOT / "bars"
TICKS_DIR = DATA_ROOT / "ticks"
MANIFESTS_DIR = DATA_ROOT / "manifests"

PHASE34_TICKS = SRC_DIR / "data" / "phase34" / "ticks_decoded"
PHASE34_RAW = SRC_DIR / "data" / "phase34" / "dukascopy_raw"

RECIPE_ID = "phase37_mt5_historical_data_qualification_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
PREFERRED_SYMBOL = "XAUUSD"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
UTC = timezone.utc

# Bounded M5 periods (UTC)
M5_PERIODS = {
    "A_recent": (datetime(2026, 9, 1, 0, 0, tzinfo=UTC), datetime(2026, 9, 29, 18, 50, tzinfo=UTC)),
    "B_middle": (datetime(2026, 6, 1, 0, 0, tzinfo=UTC), datetime(2026, 6, 30, 23, 55, tzinfo=UTC)),
    "C_early": (datetime(2026, 2, 16, 0, 0, tzinfo=UTC), datetime(2026, 2, 28, 23, 55, tzinfo=UTC)),
}

# Representative tick sample days inside each period (full-period ticks intentionally bounded)
TICK_SAMPLE_DAYS = {
    "A_recent": datetime(2026, 9, 15, 0, 0, tzinfo=UTC),
    "B_middle": datetime(2026, 6, 2, 0, 0, tzinfo=UTC),  # overlaps Phase34 local day
    "C_early": datetime(2026, 2, 16, 0, 0, tzinfo=UTC),  # overlaps Phase34 local day
}

RANGE_CHECKPOINTS = [
    datetime(2026, 2, 16, tzinfo=UTC),
    datetime(2026, 1, 1, tzinfo=UTC),
    datetime(2025, 10, 1, tzinfo=UTC),
    datetime(2025, 7, 1, tzinfo=UTC),
    datetime(2025, 1, 1, tzinfo=UTC),
    datetime(2024, 1, 1, tzinfo=UTC),
    datetime(2023, 1, 1, tzinfo=UTC),
    datetime(2022, 1, 1, tzinfo=UTC),
    datetime(2021, 1, 1, tzinfo=UTC),
    datetime(2020, 1, 1, tzinfo=UTC),
]

DST_PROBE_DATES = [
    datetime(2026, 3, 29, tzinfo=UTC),
    datetime(2026, 3, 30, tzinfo=UTC),
    datetime(2026, 10, 25, tzinfo=UTC),
    datetime(2026, 10, 26, tzinfo=UTC),
]

MAX_WALL_SECONDS = 600  # 10 minutes hard bound
FETCH_TIMEOUT_HINT_S = 90  # per-operation soft ceiling
INIT_TIMEOUT_MS = 60000

# Phase 36 Dukascopy context for speed comparison (from Phase36 bound report)
PHASE36_DUKASCOPY_CONTEXT = {
    "note": "Phase36 Dukascopy acquisition stalled on timeouts/503; ~25min wall with few complete days",
    "phase36_first_acquire_wall_min": 25.13,
    "phase36_complete_independent_days": 3,
    "phase36_verdict": "INSUFFICIENT_DATA",
}

# Local Phase37 read-only MT5 API surface (does not mutate phase12 allowlist)
PHASE37_PERMITTED_MT5_API = frozenset(
    {
        "initialize",
        "shutdown",
        "last_error",
        "terminal_info",
        "account_info",
        "symbol_info",
        "symbols_get",
        "copy_rates_from",
        "copy_rates_from_pos",
        "copy_rates_range",
        "copy_ticks_from",
        "copy_ticks_range",
        "version",
        "TIMEFRAME_M5",
        "COPY_TICKS_ALL",
        "COPY_TICKS_INFO",
        "COPY_TICKS_TRADE",
    }
)

PHASE37_PROHIBITED_MT5_API = frozenset(
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
MT5_CONNECTIONS = 0  # incremented on successful initialize in connection module
