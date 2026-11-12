"""Phase 51 constants — one-shot frozen learner confirmation."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase51"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase51"
RAW_M5 = DATA_ROOT / "mt5" / "raw" / "m5"
RAW_H1 = DATA_ROOT / "mt5" / "raw" / "h1"
RAW_TICKS = DATA_ROOT / "mt5" / "raw" / "ticks"
MANIFESTS = DATA_ROOT / "manifests"
STATE_DIR = DATA_ROOT / "state"

RECIPE_ID = "phase51_frozen_experience_learner_confirmation_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

SYMBOL = "XAUUSD"
SOURCE_SERVER_LABEL = "MetaQuotes-Demo"
TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
INIT_TIMEOUT_MS = 60000

N_DATES_TARGET = 25
MAX_TICKS_TOTAL = 12_000_000
MAX_WALL_SECONDS = 1500
MAX_RETRIES_PER_HOUR = 2
H1_WARMUP_BARS = 30
TICK_HOURS = list(range(24))

PHASE43_EXPOSURE = PROJECT_ROOT / "reports" / "phase43" / "prior_exposure_registry.json"
PHASE43_SELECTION = PROJECT_ROOT / "reports" / "phase43" / "date_selection.json"
PHASE49_SELECTION = PROJECT_ROOT / "reports" / "phase49" / "date_selection.json"

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


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
