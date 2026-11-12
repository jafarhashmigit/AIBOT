"""Phase 49 constants — ontology reset. Champion NO_MODEL / Production WAIT."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase49"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase49"
RAW_M5 = DATA_ROOT / "mt5" / "raw" / "m5"
RAW_H1 = DATA_ROOT / "mt5" / "raw" / "h1"
RAW_TICKS = DATA_ROOT / "mt5" / "raw" / "ticks"
MANIFESTS = DATA_ROOT / "manifests"
STATE_DIR = DATA_ROOT / "state"

PHASE43_EXPOSURE = PROJECT_ROOT / "reports" / "phase43" / "prior_exposure_registry.json"
PHASE43_SELECTION = PROJECT_ROOT / "reports" / "phase43" / "date_selection.json"

RECIPE_ID = "phase49_market_information_ontology_reset_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

SYMBOL = "XAUUSD"
SOURCE_SERVER_LABEL = "MetaQuotes-Demo"
TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
INIT_TIMEOUT_MS = 60000

MAX_DATES = 40
MAX_TICKS_TOTAL = 15_000_000
MAX_RETRIES_PER_HOUR = 2
MAX_WALL_SECONDS = 1800  # 30 min acquisition budget
H1_WARMUP_BARS = 30
TICK_HOURS = list(range(24))

N_DISCOVERY = 25
N_CONFIRMATION = 15
HORIZON_BARS = 12
EVENT_STRIDE = 12  # non-overlapping H12
ATR_PERIOD = 14
MIN_ATR = 1e-9

ALPHA = 0.05
N_HYPOTHESES_MAX = 18
BONFERRONI_N = 18
BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 49

RETIRED = ("H13_C", "mean_reversion", "H42_*", "H44_*")

# Phase44 validation — permanently locked
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
