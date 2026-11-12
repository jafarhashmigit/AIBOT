"""Phase 33 constants. No Phase 0–32 mutation. No package installs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase33"
DATA_ROOT = SRC_DIR / "data" / "phase33"
RAW_DIR = DATA_ROOT / "dukascopy_raw"
M5_DIR = DATA_ROOT / "dukascopy_m5"

# Read-only references (never written by Phase 33).
PHASE25_RAW_DIR = SRC_DIR / "data" / "phase25" / "dukascopy_raw"
MT5_FEATURES_PATH = SRC_DIR / "data" / "xauusd_m5_features_utc_corrected.csv"
HOLDOUT_NAME = "xauusd_m5_test.csv"
AGENT_SHADOW_DIR = SRC_DIR / "data" / "phase20" / "AGENT_SHADOW"

RECIPE_ID = "phase33_dukascopy_bidask_qualification_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H13_C_STATUS = "PAUSED_FROZEN_BENCHMARK"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF  # 2026-09-29 18:50:00
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_ID = "dukascopy_historical_bi5"
DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"
DUKASCOPY_HISTORICAL_PAGE = "https://www.dukascopy.com/swiss/english/marketwatch/historical/"
XAUUSD_PRICE_SCALE = 1000.0  # ask/bid integers ÷ 1000 → USD
POINT_SIZE = 0.01  # project price point ($0.01)
MIN_SPREAD_POINTS = 15
EXTRA_COST_ROUND_TRIP = 0.10
EXTRA_COST_PER_SIDE = EXTRA_COST_ROUND_TRIP / 2

USER_AGENT = "AIBOT-phase33-bidask-qualification/1.0 (stdlib; offline research; no redistribution)"

# Bounded diagnostic sample — representative sessions, before cutoff. Not full history.
SAMPLE_DAYS = [
    "2026-02-17",  # midweek multi-session
    "2026-03-10",  # after US DST spring-forward (2026-03-08)
    "2026-05-15",  # spring/summer midweek (EU DST in effect)
    "2026-07-08",  # summer midweek
]
# Hours UTC: Asia, London, NY, overlap, late NY — keeps download small.
SAMPLE_HOURS_UTC = [1, 8, 13, 15, 20]

# Session windows (UTC) for spread breakdown — FX metals convention used in research.
SESSION_WINDOWS_UTC = {
    "asia": (0, 7),
    "london": (7, 12),
    "new_york": (12, 21),
    "london_ny_overlap": (12, 16),
}

PROTECTED_HASHES = dict(PHASE22_PROTECTED_HASHES)

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
OCI_PROVISIONED = False
GITHUB_PUSH = False
GIT_COMMIT = False


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
