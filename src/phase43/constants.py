"""Phase 43 constants — data qualification only."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase43"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

DATA_ROOT = SRC_DIR / "data" / "phase43"
RAW_M5 = DATA_ROOT / "mt5" / "raw" / "m5"
RAW_H1 = DATA_ROOT / "mt5" / "raw" / "h1"
RAW_TICKS = DATA_ROOT / "mt5" / "raw" / "ticks"
MANIFESTS = DATA_ROOT / "manifests"
STATE_DIR = DATA_ROOT / "state"

RECIPE_ID = "phase43_independent_historical_data_expansion_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"
SOURCE_SERVER_LABEL = "MetaQuotes-Demo"
INIT_TIMEOUT_MS = 60000

WINDOW_START = date(2025, 7, 2)
WINDOW_END = date(2026, 2, 15)

MAX_DATES = 30
MAX_TICKS_TOTAL = 10_000_000
MAX_RETRIES_PER_HOUR = 2
MAX_WALL_SECONDS = 1200  # 20 minutes hard stop
H1_WARMUP_BARS = 30
TICK_HOURS = list(range(24))

# Known explicitly examined representative / eval / probe dates (Phases 34–42)
KNOWN_EVAL_OR_TARGET_DATES = frozenset(
    {
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
        "2026-09-28",
    }
)

# Phase38 coverage probe checkpoints (availability inspected)
COVERAGE_PROBE_DATES = frozenset(
    {
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
    }
)

# Phase40 additional-date plan (named but not downloaded) — still treat as mentioned;
# not PREVIOUSLY_EXPOSED for data, but not used as sole independence claim.
PHASE40_PLAN_ONLY = frozenset(
    {
        "2025-07-15",
        "2025-09-02",
        "2025-11-03",
        "2026-03-02",
        "2026-05-04",
        "2026-07-01",
        "2026-09-01",
        "2026-09-28",
    }
)

# Phase37 M5 range windows that inspected bars (inclusive calendar coverage)
PHASE37_M5_RANGES = (
    ("2026-02-16", "2026-02-27"),
    ("2026-06-01", "2026-06-30"),
    ("2026-09-01", "2026-09-29"),
)

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
