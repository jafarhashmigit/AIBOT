"""Phase 42 constants — hypothesis discovery. No H13_C / mean_reversion revival."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase42"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

PHASE40_ROOT = SRC_DIR / "data" / "phase40"
PHASE40_RAW_M5 = PHASE40_ROOT / "mt5" / "raw" / "m5"
PHASE40_RAW_H1 = PHASE40_ROOT / "mt5" / "raw" / "h1"
PHASE40_RAW_TICKS = PHASE40_ROOT / "mt5" / "raw" / "ticks"

RECIPE_ID = "phase42_autonomous_hypothesis_discovery_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

# Explicitly retired — do not optimize or revive
RETIRED_CANDIDATES = ("H13_C", "mean_reversion")

SYMBOL = "XAUUSD"
HORIZONS = (1, 3, 6, 12)  # M5 bars for forward labels
PURGE_BARS = 12  # embargo around discovery/validation boundary within a day
BONFERRONI_N = 10  # frozen frozen hypotheses
ALPHA = 0.05

# Chronological split on Phase40 dates (previously examined — not independent OOS)
ALL_DATES = [
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
DISCOVERY_DATES = ALL_DATES[:5]
VALIDATION_DATES = ALL_DATES[5:]

# Gates (frozen before scoring)
MIN_EVENTS_DISCOVERY = 40
MIN_EVENTS_VALIDATION = 25
MIN_DATES_WITH_EVENTS = 3
EFFECT_SIZE_MIN = 0.15  # |mean conditional − unconditional| in R or return units / ATR
PRED_P_BONFERRONI = ALPHA / BONFERRONI_N

SLIPPAGE_STRESS = (0.0, 0.10)
SPREAD_WIDEN = (1.0, 1.5)

BROKER_ORDERS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
HOLDOUT_ACCESSES = 0
GIT_COMMIT = False
GIT_PUSH = False
MT5_CONNECTIONS = 0


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
