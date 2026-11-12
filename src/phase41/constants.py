"""Phase 41 constants — full-session frozen retest. No strategy tuning."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase16a.constants import FROZEN_CUTS
from phase18.constants import SL_ATR_MULTIPLE, TP_ATR_MULTIPLE
from phase25.constants import STRATEGY_PARAMS

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase41"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

PHASE40_ROOT = SRC_DIR / "data" / "phase40"
PHASE40_RAW_M5 = PHASE40_ROOT / "mt5" / "raw" / "m5"
PHASE40_RAW_H1 = PHASE40_ROOT / "mt5" / "raw" / "h1"
PHASE40_RAW_TICKS = PHASE40_ROOT / "mt5" / "raw" / "ticks"
PHASE40_MANIFESTS = PHASE40_ROOT / "manifests"
PHASE40_REPORTS = PROJECT_ROOT / "reports" / "phase40"
PHASE39_REPORTS = PROJECT_ROOT / "reports" / "phase39"
PHASE36_FROZEN = PROJECT_ROOT / "reports" / "phase36" / "frozen_experiment_registry.json"

RECIPE_ID = "phase41_full_session_frozen_strategy_retest_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H13_C_STATUS = "PAUSED_FROZEN_BENCHMARK"

SYMBOL = "XAUUSD"
HORIZON_BARS = 12
TP_MULT = TP_ATR_MULTIPLE  # 1.5
SL_MULT = SL_ATR_MULTIPLE  # 1.0
TICK_HOURS = list(range(24))

TARGET_DATES = [
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

H13C_FROZEN_CUTS = dict(FROZEN_CUTS)
FROZEN_MEAN_REVERSION = dict(STRATEGY_PARAMS["mean_reversion"])

SLIPPAGE_STRESS_USD = (0.0, 0.05, 0.10, 0.20)
COMMISSION_PER_SIDE_USD = (0.0, 0.05)  # hypothetical only
SPREAD_WIDEN_MULT = (1.0, 1.5, 2.0)

MIN_INDEPENDENT_DATES_FOR_CONFIRM = 10
MIN_RESOLVED_TRADES_FOR_CONFIRM = 50
MIN_RESOLVED_FOR_ANY_CLAIM = 30
BONFERRONI_ALPHA = 0.05  # family-wise for 2 candidates

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
