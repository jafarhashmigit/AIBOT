"""Phase 34 constants. Phase 0–33 immutable. No package installs."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase34"
DATA_ROOT = SRC_DIR / "data" / "phase34"
RAW_DIR = DATA_ROOT / "dukascopy_raw"
TICKS_DIR = DATA_ROOT / "ticks_decoded"
PHASE33_RAW_DIR = SRC_DIR / "data" / "phase33" / "dukascopy_raw"
PHASE33_REPORTS = PROJECT_ROOT / "reports" / "phase33"
PHASE25_RAW_DIR = SRC_DIR / "data" / "phase25" / "dukascopy_raw"
MT5_FEATURES_PATH = SRC_DIR / "data" / "xauusd_m5_features_utc_corrected.csv"
HOLDOUT_NAME = "xauusd_m5_test.csv"

RECIPE_ID = "phase34_extended_bidask_validation_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H13_C_STATUS = "PAUSED_FROZEN_BENCHMARK"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF  # 2026-09-29 18:50:00
WINDOW_START = date(2026, 2, 16)
WINDOW_END = date(2026, 9, 29)
MAX_TRADING_DAYS = 20

SYMBOL = "XAUUSD"
DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"
XAUUSD_PRICE_SCALE = 1000.0
POINT_SIZE = 0.01
POINTS_THRESHOLDS = [15, 30, 60, 70, 100, 150]
MIN_SPREAD_POINTS_FROZEN = 15
EXTRA_COST_PER_SIDE_FROZEN = 0.05

USER_AGENT = "AIBOT-phase34-extended-bidask/1.0 (stdlib; offline research; no redistribution)"

# Download / storage bounds — prevent unbounded execution.
MAX_WALL_SECONDS = 1800  # 30 minutes acquisition budget per pass
MAX_NETWORK_HOURS = 400  # new network GETs (seeded/resumed hours do not count)
MAX_STORAGE_BYTES = 2_500_000_000  # ~2.5 GB cap
FETCH_RETRIES = 2
FETCH_TIMEOUT_S = 20
FETCH_SLEEP_S = 0.15

# FX metals daily break often ~21:00–22:00 UTC — still request all hours; empties recorded.
DOWNLOAD_HOURS_UTC = list(range(24))

SESSION_WINDOWS_UTC = {
    "asia": (0, 7),
    "london": (7, 12),
    "new_york": (12, 21),
    "london_ny_overlap": (12, 16),
}

# Civil DST 2026 (stdlib only — no tzdata). Source: US/EU published rules.
DST_2026 = {
    "us_start_utc": "2026-03-08 07:00:00",  # 02:00 EST → EDT
    "us_end_utc": "2026-11-01 06:00:00",
    "eu_start_utc": "2026-03-29 01:00:00",  # 01:00 CET → CEST
    "eu_end_utc": "2026-10-25 01:00:00",
}

# Phase 33 reference spreads (reported).
PHASE33_SPREAD_REF = {
    "median_usd": 0.70,
    "mean_usd": 0.71,
    "p95_usd": 1.01,
    "n_ticks": 445108,
}

PROTECTED_HASHES = dict(PHASE22_PROTECTED_HASHES)

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
GIT_COMMIT = False
GIT_PUSH = False


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def select_trading_days(n: int = MAX_TRADING_DAYS) -> list[str]:
    """Deterministic Mon–Fri selection across window, forcing DST-adjacent weekdays."""
    weekdays: list[date] = []
    d = WINDOW_START
    while d <= WINDOW_END:
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            weekdays.append(d)
        d += timedelta(days=1)

    forced = {
        date(2026, 3, 6),   # Fri before US DST
        date(2026, 3, 9),   # Mon after US DST
        date(2026, 3, 27),  # Fri before EU DST
        date(2026, 3, 30),  # Mon after EU DST
        date(2026, 2, 17),  # Phase25/33 overlap
        date(2026, 3, 10),
        date(2026, 5, 15),
        date(2026, 7, 8),
        date(2026, 9, 15),
        date(2026, 9, 28),  # near cutoff (Mon)
    }
    forced = sorted(x for x in forced if WINDOW_START <= x <= WINDOW_END and x.weekday() < 5)

    if n >= len(weekdays):
        selected = weekdays
    else:
        # Evenly spaced indices, then union forced days, trim to n preferring forced.
        step = (len(weekdays) - 1) / max(n - 1, 1)
        spaced = []
        for i in range(n):
            idx = int(round(i * step))
            spaced.append(weekdays[min(idx, len(weekdays) - 1)])
        selected_set = set(spaced) | set(forced)
        selected = sorted(selected_set)
        # If over n, keep all forced and fill with evenly spaced remainder.
        if len(selected) > n:
            keep = set(forced)
            for day in spaced:
                if len(keep) >= n:
                    break
                keep.add(day)
            selected = sorted(keep)[:n]
        elif len(selected) < n:
            for day in weekdays:
                if len(selected) >= n:
                    break
                if day not in selected:
                    selected.append(day)
            selected = sorted(selected)[:n]

    return [x.isoformat() for x in selected]
