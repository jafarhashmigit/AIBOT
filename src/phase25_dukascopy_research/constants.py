"""Phase 25 constants. Tolerances frozen before evaluation. No Phase 16A–24 edits."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase25"
DATA_ROOT = SRC_DIR / "data" / "phase25"
RAW_DIR = DATA_ROOT / "dukascopy_raw"
M5_DIR = DATA_ROOT / "dukascopy_m5"
MT5_FEATURES_PATH = SRC_DIR / "data" / "xauusd_m5_features_utc_corrected.csv"

RECIPE_ID = "phase25_dukascopy_mt5_parity_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF  # 2026-09-29 18:50:00
HOLDOUT_NAME = "xauusd_m5_test.csv"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SOURCE_ID = "dukascopy_historical_bi5"
DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"
XAUUSD_PRICE_SCALE = 1000.0  # documented community/official tooling scale for XAUUSD ticks

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
OCI_PROVISIONED = False
GITHUB_PUSH = False

# ---------------------------------------------------------------------------
# FROZEN PARITY TOLERANCES — declared BEFORE evaluating Dukascopy vs MT5.
# Do not loosen after seeing results.
# ---------------------------------------------------------------------------
FROZEN_TOLERANCES = {
    "freeze_note": "Declared prior to Phase 25 evaluation; not adjusted post-hoc.",
    "min_common_coverage_of_mt5": 0.95,
    "max_duplicate_fraction": 0.0,
    "median_abs_close_usd": 0.50,
    "p95_abs_close_usd": 2.00,
    "max_abs_close_usd": 5.00,
    "median_abs_atr14_usd": 0.50,
    "median_abs_close_to_ema_20": 5e-4,
    "median_abs_ema_9_20_spread": 5e-4,
    "h13c_action_agreement_min": 0.99,
    "price_side_for_primary": "mid",  # mid = (bid+ask)/2 OHLC; also report bid/ask
}

# Multi-day approved windows (all <= RESEARCH_CUTOFF). Mix sessions via full UTC days.
PARITY_DAYS = [
    "2026-02-17",  # overlap with Phase 24 AlgoSpecial window; Asia/London/NY hours
    "2026-03-10",  # midweek multi-session (Asia/London/NY)
]

# Hours UTC to attempt per day (FX metals; empties expected around weekend/daily break).
DOWNLOAD_HOURS_UTC = list(range(0, 24))

USER_AGENT = "AIBOT-phase25-parity-research/1.0 (stdlib; no redistribution)"

# Feature columns comparable when recomputed from OHLC (exclude calendar/session/volume-z).
OHLC_RECOMPUTE_FEATURES = [
    "ema_9",
    "ema_20",
    "ema_50",
    "close_to_ema_9",
    "close_to_ema_20",
    "close_to_ema_50",
    "ema_9_20_spread",
    "ema_20_50_spread",
    "atr_14",
    "atr_14_pct",
    "log_return_1",
    "return_1",
    "return_3",
    "return_6",
    "return_12",
    "momentum_10",
    "roc_10",
    "momentum_20",
    "roc_20",
    "candle_body",
    "candle_body_abs",
    "upper_wick",
    "lower_wick",
    "candle_range",
]

from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES  # noqa: E402
