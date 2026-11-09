"""Phase 21 constants. Does not modify Phase 14–20 behavior."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase16a.constants import FROZEN_CUTS

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase21"

RECIPE_ID = "phase21_h13c_threshold_reachability_v1"
SEED = 42

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE_STATUS = "EXPERIMENTAL"
RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"

# Exact frozen Phase 14 WF3 cuts — never replaced by newly computed quantiles.
FROZEN_WF3_CUTS = dict(FROZEN_CUTS)

# Research-only sensitivity percentiles (not applied to agent).
SENSITIVITY_Q_LOWS = (25, 20, 15, 10, 5)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
DISCORD_MESSAGES = 0

PROTECTED_HASHES = {
    "src/phase14/strategy.py": "68db400ceae47495934b65e464e8f51a593611ef60b5438c09967b59bd76d69b",
    "src/phase16a/constants.py": "428327ae992e8c562b40d255b7f3fb2665f5b0bf77b771354e0e6a157233e926",
    "src/phase16a/predictor.py": "1ff5ffb49fa31a8bc7e1f130ca436f33eb990d97f0afdfafda0c622f06f5e81d",
}
