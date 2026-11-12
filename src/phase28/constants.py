"""Phase 28 constants. Frozen artifacts referenced; no retuning on forward data."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase14.constants import PRIMARY_PULLBACK_Q_HIGH, PRIMARY_PULLBACK_Q_LOW
from phase16a.constants import FROZEN_CUTS
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES
from phase27.constants import PHASE26_ACCEPTED, REGIME_METHOD

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
PHASE28_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data" / "phase28"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase28"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
ARTIFACTS_DIR = PHASE28_DIR / "artifacts"
FROZEN_VOL_PATH = ARTIFACTS_DIR / "frozen_vol_model_v1.json"

RECIPE_ID = "phase28_forward_shadow_validation_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"
PHASE25_VERDICT = "NO_NEW_EDGE_FOUND"
PHASE26_VERDICT = "PROMISING_BUT_UNCONFIRMED"
PHASE27_VERDICT = "PROMISING_BUT_UNCONFIRMED"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"
MAX_DECISION_TIME_UTC = "2026-09-29 17:50:00"

# Frozen Phase 14 / 16A WF3 cuts — never recomputed from forward data.
FROZEN_WF3_CUTS = dict(FROZEN_CUTS)
H13C_Q_LOW = PRIMARY_PULLBACK_Q_LOW
H13C_Q_HIGH = PRIMARY_PULLBACK_Q_HIGH

OBSERVER_BASELINE = "H13C_BASELINE"
OBSERVER_HIGH_VOL = "H13C_HIGH_VOL_RESEARCH"
SOURCE_SHADOW = "AGENT_SHADOW"
SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"

# Phase 27 high-only policy: accept H13_C BUY/SELL only when pred regime == high.
HIGH_ONLY_REGIME = "high"
REGIME_METHOD_FROZEN = REGIME_METHOD  # train_predicted_vol_tertiles

# Frozen vol model uses Phase 26 accepted orthogonal features (OHLC-computable).
FROZEN_VOL_FEATURES = tuple(PHASE26_ACCEPTED)
FROZEN_VOL_TRAIN_CUTOFF = FROZEN_CUTS["train_cutoff"]  # WF3 train cutoff
FROZEN_VOL_RIDGE_ALPHA = 1.0
FROZEN_VOL_SEED = 42

DEFAULT_SESSION_MAX_CANDLES = 100
CAMPAIGN_TARGET_CANDLES = 1000  # campaign progress target; not a validation claim
DEFAULT_POLL_INTERVAL_SECONDS = 15

# Predeclared evidence gates for exiting INSUFFICIENT_FORWARD_EVIDENCE.
EVIDENCE_GATES = {
    "min_new_forward_candles": 500,
    "min_baseline_buy_sell_decisions": 50,
    "min_high_only_accepted_decisions": 30,
    "min_matured_outcomes_h12": 30,
    "min_distinct_trading_days": 10,
}

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
HORIZONS = tuple(range(1, 13))

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
OCI_PROVISIONED = False
GITHUB_PUSH = False
AUTONOMOUS_RETRAIN = False


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
