"""Phase 46 constants — costed EV foundation. No strategy discovery."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase46"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_OUT_DIR = SRC_DIR / "data" / "phase46"

PHASE43_ROOT = SRC_DIR / "data" / "phase43"
PHASE43_RAW_M5 = PHASE43_ROOT / "mt5" / "raw" / "m5"
PHASE43_RAW_TICKS = PHASE43_ROOT / "mt5" / "raw" / "ticks"

RECIPE_ID = "phase46_costed_expected_value_foundation_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

SYMBOL = "XAUUSD"
SOURCE_SERVER_LABEL = "MetaQuotes-Demo"

# Frozen M5 horizon for foundation outcomes (12×5m = 60m)
HORIZON_BARS = 12
ATR_PERIOD = 14
# Risk floor: if ATR missing/zero, outcome marked INVALID_RISK (no silent substitute)
MIN_ATR = 1e-9

# Phase44 discovery dates — already exposed; engineering/diagnostic ONLY
ENGINEERING_DATES = [
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

# Phase44 validation — FORBIDDEN for discovery, fitting, and this foundation eval set
FORBIDDEN_VALIDATION_DATES = frozenset(
    {
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
    }
)

RETIRED_DO_NOT_REVIVE = ("H13_C", "mean_reversion", "H42_*", "H44_*")

# Bootstrap for diagnostic CIs (not strategy claim)
BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 46
ALPHA = 0.05

# Cap engineering sample for runtime (every Nth decision bar); 1 = all eligible
DECISION_STRIDE = 1
# Soft cap on outcome rows written (full-day always-BUY is large); 0 = no cap
MAX_OUTCOMES_PER_ACTION_PER_DAY = 0

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


def canonical_json_sha256(obj: object) -> str:
    import json

    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
