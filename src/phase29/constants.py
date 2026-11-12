"""Phase 29 constants. Frozen Phase 14/27/28 logic referenced; no retuning."""

from __future__ import annotations

import hashlib
from pathlib import Path

from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase14.constants import PRIMARY_PULLBACK_Q_HIGH, PRIMARY_PULLBACK_Q_LOW
from phase16a.constants import FROZEN_CUTS
from phase22.constants import PROTECTED_HASHES as PHASE22_PROTECTED_HASHES
from phase27.constants import REGIME_METHOD
from phase28.constants import (
    FROZEN_VOL_FEATURES,
    FROZEN_VOL_PATH,
    HIGH_ONLY_REGIME,
    OBSERVER_BASELINE,
    OBSERVER_HIGH_VOL,
)

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
PHASE29_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data" / "phase29"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase29"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

RECIPE_ID = "phase29_forward_shadow_continuation_v1"
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
H13C_STATUS = "EXPERIMENTAL"
PRODUCTION_FINAL_ACTION = "WAIT"
PHASE28_STATUS = "INSUFFICIENT_FORWARD_EVIDENCE"

RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF
HOLDOUT_NAME = "xauusd_m5_test.csv"

FROZEN_WF3_CUTS = dict(FROZEN_CUTS)
H13C_Q_LOW = PRIMARY_PULLBACK_Q_LOW
H13C_Q_HIGH = PRIMARY_PULLBACK_Q_HIGH
REGIME_METHOD_FROZEN = REGIME_METHOD
HIGH_ONLY_REGIME_LABEL = HIGH_ONLY_REGIME

OBSERVER_A = OBSERVER_BASELINE  # H13C_BASELINE
OBSERVER_B = OBSERVER_HIGH_VOL  # H13C_HIGH_VOL_RESEARCH
SOURCE_SHADOW = "AGENT_SHADOW"
SOURCE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
STRATEGY_ID = "H13_C"

# Campaign evidence / continuation targets (not a validation claim by themselves).
MIN_FORWARD_CANDLES = 200
MIN_BUY_SELL_DECISIONS = 5
MIN_MATURED_OUTCOMES = 5
DEFAULT_POLL_INTERVAL_SECONDS = 15
DEFAULT_SESSION_MAX_CANDLES = None  # None = continue until campaign targets

# Discord: BUY/SELL on by default for live mode; WAIT off to avoid spam.
DEFAULT_DISCORD_WAIT = False

FROZEN_VOL_ARTIFACT = FROZEN_VOL_PATH
FROZEN_VOL_FEATURE_NAMES = FROZEN_VOL_FEATURES

BROKER_ORDERS = 0
HOLDOUT_ACCESSES = 0
MT5_CONNECTIONS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
GITHUB_PUSH = False


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_hash_snapshot() -> dict:
    out = {}
    for rel, expected in PHASE22_PROTECTED_HASHES.items():
        p = PROJECT_ROOT / rel
        actual = sha256_file(p) if p.exists() else None
        out[rel] = {
            "expected": expected,
            "actual": actual,
            "match": actual == expected if actual is not None else False,
        }
    return out
