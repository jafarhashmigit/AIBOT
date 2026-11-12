"""Phase 52 constants — market selection audit only."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase52"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase52_market_representation_selection_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
INIT_TIMEOUT_MS = 60000

# Cap: max 10 instruments × 3 TFs = 30
CANDIDATE_INSTRUMENTS = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "XAGUSD",
]
TIMEFRAMES = ("M5", "M15", "H1")

# Bounded coverage probe window (UTC calendar) — not strategy eval dates
PROBE_START = "2025-10-01"
PROBE_END = "2025-12-15"
# Tick sample: 3 hours on one mid probe day only (not unbounded)
TICK_SAMPLE_DAY = "2025-11-05"
TICK_SAMPLE_HOURS = (8, 13, 18)

# Existing archives to reuse first
PHASE43_M5 = SRC_DIR / "data" / "phase43" / "mt5" / "raw" / "m5"
PHASE43_TICKS = SRC_DIR / "data" / "phase43" / "mt5" / "raw" / "ticks"
PHASE49_M5 = SRC_DIR / "data" / "phase49" / "mt5" / "raw" / "m5"
PHASE49_TICKS = SRC_DIR / "data" / "phase49" / "mt5" / "raw" / "ticks"
PHASE51_M5 = SRC_DIR / "data" / "phase51" / "mt5" / "raw" / "m5"
PHASE51_TICKS = SRC_DIR / "data" / "phase51" / "mt5" / "raw" / "ticks"

# Score weights (data quality / research suitability — NOT profitability)
WEIGHTS = {
    "historical_coverage": 0.20,
    "bid_ask_availability": 0.20,
    "spread_quality": 0.20,
    "session_completeness": 0.15,
    "data_integrity": 0.15,
    "usable_sample_size": 0.10,
}

MIN_QUALIFIED_SCORE = 0.55

BROKER_ORDERS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
HOLDOUT_ACCESSES = 0
GIT_COMMIT = False
GIT_PUSH = False
MT5_CONNECTIONS = 0


def canonical_json_sha256(obj: object) -> str:
    import json

    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
