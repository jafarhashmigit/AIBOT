"""Phase 44 constants — independent edge discovery on Phase43 UNSEEN dates."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase44"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

PHASE43_ROOT = SRC_DIR / "data" / "phase43"
PHASE43_RAW_M5 = PHASE43_ROOT / "mt5" / "raw" / "m5"
PHASE43_RAW_H1 = PHASE43_ROOT / "mt5" / "raw" / "h1"
PHASE43_RAW_TICKS = PHASE43_ROOT / "mt5" / "raw" / "ticks"
PHASE43_MANIFESTS = PHASE43_ROOT / "manifests"
PHASE43_REPORTS = PROJECT_ROOT / "reports" / "phase43"

RECIPE_ID = "phase44_preregistered_independent_edge_discovery_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

RETIRED = ("H13_C", "mean_reversion")
PHASE42_REJECTED_PREFIX = "H42_"

SYMBOL = "XAUUSD"
HORIZONS = (1, 3, 6, 12)
PURGE_BARS = 12
MAX_HYPOTHESES = 5
BONFERRONI_N = 5
ALPHA = 0.05

# Exact Phase43 allocation — never reallocate
DISCOVERY_DATES = [
    "2025-07-02",
    "2025-07-09",
    "2025-07-16",
    "2025-07-23",
    "2025-07-30",
    "2025-08-06",
    "2025-08-20",
    "2025-08-27",
    "2025-09-04",
    "2025-09-11",
    "2025-09-18",
    "2025-09-24",
    "2025-10-07",
    "2025-10-14",
    "2025-10-20",
]
VALIDATION_DATES = [
    "2025-10-27",
    "2025-10-31",
    "2025-11-10",
    "2025-11-17",
    "2025-11-21",
    "2025-12-04",
    "2025-12-11",
    "2025-12-17",
    "2025-12-24",
    "2025-12-31",
    "2026-01-07",
    "2026-01-20",
    "2026-01-27",
    "2026-02-03",
    "2026-02-10",
]

MIN_EVENTS_DISCOVERY = 50
MIN_EVENTS_VALIDATION = 40
MIN_DATES_WITH_EVENTS = 5
EFFECT_SIZE_MIN = 0.12
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
