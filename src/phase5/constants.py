"""Phase 5 constants. Frozen hypothesis. No tuning."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase5"

INDEPENDENT_RAW = DATA_DIR / "phase5_independent_m5.csv"
INDEPENDENT_FEATURES = DATA_DIR / "phase5_independent_features.csv"
INDEPENDENT_OUTCOMES = DATA_DIR / "phase5_independent_sell_outcomes.csv"

SEED = 42
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
RESEARCH_CUTOFF = "2026-09-29 18:50:00"
# First bar of the approved M5 file. Independent bars must be strictly before this.
APPROVED_M5_START = "2026-02-16 08:50:00"
HOLDOUT_NAME = "xauusd_m5_test.csv"
RECIPE_ID = "phase5_ny_sell_replication_v1"

MT5_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"

BAR_MINUTES = 5
HORIZON_BARS = 12
TP_ATR_MULTIPLE = 1.5
SL_ATR_MULTIPLE = 1.0
ATR_PERIOD = 14
POINT_SIZE = 0.01
MIN_SPREAD_POINTS = 15
EXTRA_COST_PER_SIDE = 0.05
SPREAD_FLOOR_USD = MIN_SPREAD_POINTS * POINT_SIZE

SERVER_TZ = "Europe/Athens"
NY_TZ = "America/New_York"
LONDON_TZ = "Europe/London"
NY_START_HOUR = 8
NY_END_HOUR = 17
LONDON_START_HOUR = 8
LONDON_END_HOUR = 17

PHASE2_OOS_SHA256 = "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f"
PHASE4_RESULT_SHA16 = "c8565408b35f66c7"

PHASE4_REFERENCE = {
    "slice": "regime_session:new_york:SELL",
    "n": 1710,
    "mean_r": 0.03601854381735814,
    "profit_factor": 1.0924086229715078,
    "stress_mean_r_x1_5": 0.020518039766491705,
    "ci": [-0.08752073063882865, 0.15966930603197058],
}

N_BOOT = 2000
SPREAD_STRESS = (1.5, 2.0)
