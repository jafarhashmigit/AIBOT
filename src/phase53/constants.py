"""Phase 53 constants — final costed decision-edge development on XAUUSD/M5."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase53"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase53"
RAW_M5 = DATA_ROOT / "mt5" / "raw" / "m5"
RAW_H1 = DATA_ROOT / "mt5" / "raw" / "h1"
RAW_TICKS = DATA_ROOT / "mt5" / "raw" / "ticks"
MANIFESTS = DATA_ROOT / "manifests"
STATE_DIR = DATA_ROOT / "state"

RECIPE_ID = "phase53_costed_decision_edge_development_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_SERVER_LABEL = "MetaQuotes-Demo"
TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
INIT_TIMEOUT_MS = 60000

PHASE43_EXPOSURE = PROJECT_ROOT / "reports" / "phase43" / "prior_exposure_registry.json"
PHASE43_SELECTION = PROJECT_ROOT / "reports" / "phase43" / "date_selection.json"
PHASE44_ALLOCATION = PROJECT_ROOT / "reports" / "phase44" / "allocation_lock.json"
PHASE49_SELECTION = PROJECT_ROOT / "reports" / "phase49" / "date_selection.json"
PHASE51_SELECTION = PROJECT_ROOT / "reports" / "phase51" / "date_selection.json"
PHASE50_REPORT = PROJECT_ROOT / "reports" / "phase50" / "FINAL_REPORT.md"
PHASE52_REPORT = PROJECT_ROOT / "reports" / "phase52" / "FINAL_REPORT.md"

N_DATES_TARGET = 30
N_DISCOVERY = 20
N_CONFIRMATION = 10
MAX_TICKS_TOTAL = 12_000_000
MAX_WALL_SECONDS = 2100
MAX_RETRIES_PER_HOUR = 2
H1_WARMUP_BARS = 30
TICK_HOURS = list(range(24))

HORIZON_BARS = 12
EVENT_STRIDE = 12
ATR_PERIOD = 14

N_FAMILIES = 3
BONFERRONI_N = 3
ALPHA = 0.05
BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 53

# Preregistered economic thresholds (not searched)
CMC_MIN_ABS_DISP_ATR = 0.50
CMC_MAX_SPREAD_ATR = 0.20
EXF_MIN_ABS_CONSEC = 6
EXF_MAX_IMPULSE_RETR = 0.50
EXF_MAX_SPREAD_ATR = 0.20
SLF_REQUIRE_OVERLAP = True
SLF_MAX_SPREAD_DELTA = 0.0

MIN_DISCOVERY_DATES = 8
MIN_CONFIRMATION_DATES = 5
MIN_POLICY_TRADES = 25

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
