"""Phase 54 — autonomous paper-trading agent engineering (XAUUSD/M5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase54"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase54"
STATE_DIR = DATA_ROOT / "state"
HIST_EXP_DIR = DATA_ROOT / "HISTORICAL_HYPOTHETICAL"
SHADOW_EXP_DIR = DATA_ROOT / "AGENT_SHADOW"
LEDGER_DIR = DATA_ROOT / "ledger"
POSITIONS_DIR = DATA_ROOT / "positions"

RECIPE_ID = "phase54_autonomous_bot_engineering_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
POLICY_VERSION = "phase54_null_policy_v1"
FEATURE_VERSION = "phase49_features_v1"
AGENT_VERSION = "phase54_paper_agent_v1"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
HORIZON_BARS = 12
EVENT_STRIDE = 12
ATR_PERIOD = 14

# Default risk config — conservative, not claimed profitable
DEFAULT_RISK = {
    "max_risk_per_trade_r": 1.0,
    "max_simultaneous_positions": 1,
    "max_daily_loss_r": 3.0,
    "max_drawdown_r": 5.0,
    "max_spread_atr": 0.25,
    "max_spread_price": 1.0,
    "stop_atr_multiple": 1.0,
    "circuit_breaker_errors": 5,
}

# Replay defaults
DEFAULT_MAX_CANDLES = 5000
DEFAULT_REPLAY_ARCHIVE = SRC_DIR / "data" / "phase53" / "mt5" / "raw"

PHASE49_CONFIRMATION = PROJECT_ROOT / "reports" / "phase49" / "date_selection.json"
PHASE44_VALIDATION = frozenset(
    {
        "2025-10-27",
        "2025-10-31",
        "2025-11-10",
        "2025-11-17",
        "2025-11-21",
        "2025-12-04",
        "2025-12-11",
        "2025-12-17",
        "2025-12-24",
        "2025-12-31",
        "2026-01-07",
        "2026-01-20",
        "2026-01-27",
        "2026-02-03",
        "2026-02-10",
    }
)

BROKER_ORDERS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
HOLDOUT_ACCESSES = 0
GIT_COMMIT = False
GIT_PUSH = False
MT5_LIVE_CONNECTIONS = 0


def canonical_json_sha256(obj: object) -> str:
    import json

    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
