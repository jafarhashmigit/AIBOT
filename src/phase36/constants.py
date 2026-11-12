"""Phase 36 constants. Phase 0–35 immutable. No package installs. No MT5."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase18.constants import EXTRA_COST_PER_SIDE, SL_ATR_MULTIPLE, TP_ATR_MULTIPLE
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES
from phase25.constants import STRATEGY_PARAMS

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase36"
DATA_ROOT = SRC_DIR / "data" / "phase36"
RAW_DIR = DATA_ROOT / "dukascopy_raw"
TICKS_DIR = DATA_ROOT / "ticks_decoded"

PHASE34_RAW = SRC_DIR / "data" / "phase34" / "dukascopy_raw"
PHASE34_TICKS = SRC_DIR / "data" / "phase34" / "ticks_decoded"
PHASE33_RAW = SRC_DIR / "data" / "phase33" / "dukascopy_raw"
PHASE25_RAW = SRC_DIR / "data" / "phase25" / "dukascopy_raw"
PHASE35_REPORTS = PROJECT_ROOT / "reports" / "phase35"
# Read-only seed roots for non-excluded selected days (never Phase34/35 eval days).
SEED_RAW_DIRS = (PHASE34_RAW, PHASE33_RAW, PHASE25_RAW)

RECIPE_ID = "phase36_mean_reversion_replication_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
WINDOW_START = date(2026, 2, 16)
WINDOW_END = date(2026, 9, 29)

# Phase 34/35 evaluated complete days — FORBIDDEN for independent replication.
EXCLUDED_EVAL_DAYS = frozenset(
    {
        "2026-02-17",
        "2026-03-06",
        "2026-03-10",
        "2026-05-15",
        "2026-07-08",
        "2026-09-15",
    }
)

MAX_SELECTED_DATES = 20
MAX_RETRIES_PER_HOUR = 2
FETCH_TIMEOUT_S = 20
FETCH_SLEEP_S = 0.2
MAX_WALL_SECONDS = 1500  # 25 min acquisition budget
MAX_CONSECUTIVE_NETWORK_FAILURES = 12  # stop on sustained 503/timeout stalls
MIN_COMPLETE_DAYS_FOR_REPLICATION = 10
MIN_RESOLVED_TRADES_FOR_REPLICATION = 100

HORIZON_BARS = 12
TP_MULT = TP_ATR_MULTIPLE
SL_MULT = SL_ATR_MULTIPLE
POINT_SIZE = 0.01

# Frozen mean_reversion params — copied from Phase25 STRATEGY_PARAMS before eval.
FROZEN_MEAN_REVERSION_PARAMS = dict(STRATEGY_PARAMS["mean_reversion"])

DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"
SYMBOL = "XAUUSD"
XAUUSD_PRICE_SCALE = 1000.0
USER_AGENT = "AIBOT-phase36-mr-replication/1.0 (stdlib; offline research)"

PROTECTED_HASHES = dict(PHASE22_PROTECTED_HASHES)

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
GIT_COMMIT = False
GIT_PUSH = False


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
