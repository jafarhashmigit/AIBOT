"""Phase 22 constants. Does not modify Phase 14–21 behavior."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID
from phase16a.constants import FROZEN_CUTS

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data" / "phase22"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase22"

# Never write into these stores.
PHASE20_DATA = SRC_DIR / "data" / "phase20"
PHASE19_SYNTHETIC = SRC_DIR / "data" / "phase19" / "PHASE19_SYNTHETIC_TEST"
PHASE18_DATA = SRC_DIR / "data" / "phase18"

RECIPE_ID = "phase22_extended_forward_observation_v1"
SEED = 42

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE = "H13_C_H1_PULLBACK"
CANDIDATE_STATUS = "EXPERIMENTAL"
STRATEGY_ID = "H13_C"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_TYPE = "FORWARD_SHADOW"
SOURCE_SHADOW = "AGENT_SHADOW"
SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"
SOURCE_SYNTHETIC = "PHASE19_SYNTHETIC_TEST"

SELECTED_HORIZON_DISPLAY = "NOT ESTABLISHED"
SHADOW_DISCLAIMER = "AIBOT SHADOW — NOT A REAL TRADING SIGNAL"

CAMPAIGN_TARGET_CANDLES = 1000
DEFAULT_SESSION_MAX_CANDLES = 100
DEFAULT_POLL_INTERVAL_SECONDS = 15

# Phase 21 historical reachability (condition frequencies, not live trade rates).
PHASE21_HISTORICAL_BUY_RATE = 0.006666666666666667
PHASE21_HISTORICAL_SELL_RATE = 0.00944640753828033
PHASE21_HISTORICAL_N = 42450
PHASE21_HISTORICAL_BUY_N = 283
PHASE21_HISTORICAL_SELL_N = 401

FROZEN_WF3_CUTS = dict(FROZEN_CUTS)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
AUTO_START_DISABLED = True

PROTECTED_HASHES = {
    "src/phase16a/constants.py": "428327ae992e8c562b40d255b7f3fb2665f5b0bf77b771354e0e6a157233e926",
    "src/phase16a/predictor.py": "1ff5ffb49fa31a8bc7e1f130ca436f33eb990d97f0afdfafda0c622f06f5e81d",
    "src/phase18/outcomes.py": "b4bbfc481606d33a3d5f2cd25422adbb45d5fa68e891b1cdfeac542099d64464",
    "src/phase18/barrier.py": "4db1972b52a47f3b8ef510d62ac1e6fca5763950ca190457271ff275c548f06d",
    "src/phase18/experience.py": "eab2109d62ec3dd36615395cc70ab39fa9c0bf8b1eb9e055e22b7f103200335c",
    "src/phase18/store.py": "079458f58df8fef99f827ae00fbc5639e10735fe8d32714711492351813e0416",
    "src/phase20/loop.py": "542f4a84c85578c33c68b4a0b7143b2226026aa3da7d6b059f8f4dc9b1d16e0f",
    "src/phase20/constants.py": "13dc30b30ea1d04c80a7fc41da724736e71b64671d0012d26eb3c8efc74460c0",
    "src/phase20/messages.py": "58d041566f5a885ae3aa18f8a2f5225f1ac4d5d10bc5e3120036265877525b55",
    "src/phase20/candles.py": "03027a4739c1e1651fdf9721518c2acfff581e8ad5683afda2cd2699103e3eda",
    "src/phase21/constants.py": "c12a784fbb80ed2759283c2075e06fecfd9d92c2808d3322aceb086c229f6e40",
    "src/phase21/analysis.py": "03b9cb8187c1c81684a8b35872790006e142d187db9fbd0dd9786d82580e7c55",
}
