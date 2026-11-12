"""Phase 39 constants — execution reality & edge validation. No strategy tuning."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase16a.constants import FROZEN_CUTS
from phase18.constants import SL_ATR_MULTIPLE, TP_ATR_MULTIPLE
from phase25.constants import STRATEGY_PARAMS

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase39"
PHASE38_RAW_M5 = SRC_DIR / "data" / "phase38" / "mt5" / "raw" / "m5"
PHASE38_RAW_TICKS = SRC_DIR / "data" / "phase38" / "mt5" / "raw" / "ticks"
PHASE38_MANIFESTS = SRC_DIR / "data" / "phase38" / "manifests"
PHASE36_FROZEN = PROJECT_ROOT / "reports" / "phase36" / "frozen_experiment_registry.json"
PHASE35_REPORTS = PROJECT_ROOT / "reports" / "phase35"
PHASE34_TICKS = SRC_DIR / "data" / "phase34" / "ticks_decoded"

RECIPE_ID = "phase39_execution_reality_edge_validation_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H13_C_STATUS = "PAUSED_FROZEN_BENCHMARK"

SYMBOL = "XAUUSD"
POINT_SIZE = 0.01
HORIZON_BARS = 12
TP_MULT = TP_ATR_MULTIPLE  # 1.5
SL_MULT = SL_ATR_MULTIPLE  # 1.0

# Frozen from Phase16A / Phase35 — not re-optimized
H13C_FROZEN_CUTS = dict(FROZEN_CUTS)

# Frozen from Phase25 / Phase36 registry — must match exactly
FROZEN_MEAN_REVERSION = dict(STRATEGY_PARAMS["mean_reversion"])

# Phase38 tick windows are 12:00–15:00 UTC (3h)
TICK_WINDOW_START_HOUR = 12
TICK_WINDOW_END_HOUR = 15

# Stress scenarios (hypothetical; NOT observed live costs)
SLIPPAGE_STRESS_USD = (0.0, 0.05, 0.10, 0.20)
COMMISSION_PER_SIDE_USD = (0.0, 0.05)  # hypothetical only
SPREAD_WIDEN_MULT = (1.0, 1.5, 2.0)

MIN_INDEPENDENT_DATES_FOR_CONFIRM = 10
MIN_RESOLVED_TRADES_FOR_CONFIRM = 50
MIN_RESOLVED_FOR_ANY_CLAIM = 30

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
