"""Phase 35 constants. Phase 0–34 immutable. No package installs. No MT5."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase16a.constants import FROZEN_CUTS
from phase18.constants import EXTRA_COST_PER_SIDE, SL_ATR_MULTIPLE, TP_ATR_MULTIPLE
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase35"
PHASE34_REPORTS = PROJECT_ROOT / "reports" / "phase34"
PHASE34_RAW = SRC_DIR / "data" / "phase34" / "dukascopy_raw"
PHASE34_TICKS = SRC_DIR / "data" / "phase34" / "ticks_decoded"

RECIPE_ID = "phase35_historical_execution_revaluation_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H13_C_STATUS = "PAUSED_FROZEN_BENCHMARK"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"
POINT_SIZE = 0.01
MIN_SPREAD_POINTS_FROZEN = 15
EXTRA_COST_PER_SIDE_FROZEN = EXTRA_COST_PER_SIDE  # 0.05 — VIEW B only
HORIZON_BARS = 12
TP_MULT = TP_ATR_MULTIPLE  # 1.5
SL_MULT = SL_ATR_MULTIPLE  # 1.0

# Frozen H13_C cuts — read-only reference, not re-optimized.
H13C_FROZEN_CUTS = dict(FROZEN_CUTS)

# Sample-size discipline for 6-day corpus
MIN_RESOLVED_FOR_EVAL = 30
MIN_RESOLVED_FOR_PROMISING = 50

PROTECTED_HASHES = dict(PHASE22_PROTECTED_HASHES)

PHASE34_IMMUTABLE_REPORTS = (
    "reports/phase34/final_verdict.json",
    "reports/phase34/acquisition_manifest.json",
    "reports/phase34/spread_analysis.json",
)

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
GIT_COMMIT = False
GIT_PUSH = False


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
