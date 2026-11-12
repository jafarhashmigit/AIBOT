"""Unified signal orchestrator constants — shadow-only publication by default."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SRC_DIR.parent
DATA_ROOT = SRC_DIR / "data" / "signal_orchestrator"
SERVICE_DIR = DATA_ROOT / "service"
DECISIONS_PATH = DATA_ROOT / "decisions.jsonl"
DELIVERY_LEDGER_PATH = DATA_ROOT / "delivery_ledger.jsonl"
DELIVERY_QUEUE_PATH = DATA_ROOT / "delivery_queue.jsonl"
DEAD_LETTER_PATH = DATA_ROOT / "delivery_dead_letter.jsonl"
STATE_PATH = SERVICE_DIR / "orchestrator_state.json"
PID_PATH = SERVICE_DIR / "orchestrator.pid"
LOG_PATH = SERVICE_DIR / "orchestrator.log"
REPORTS_DIR = PROJECT_ROOT / "reports" / "completion"

ORCHESTRATOR_VERSION = "signal_orchestrator_v1_prompt06"
SERVICE_VERSION = "signal_orchestrator_service_v1"

SYMBOL = "XAUUSDm"
TIMEFRAME = "M5"
USER_TZ = "Asia/Karachi"

# Safety posture
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H70_STATUS = "FROZEN_UNVALIDATED"
STRATEGY_APPROVAL = "NOT_APPROVED"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
ORDER_SEND = "PROHIBITED"
BROKER_COLLECTION = "READ_ONLY"
EXECUTION_AUTHORIZATION = "BLOCKED"
RISK_POLICY = "UNAPPROVED"
COMMISSION = "UNKNOWN"
SWAP = "UNKNOWN_FOR_EXECUTION"
MARGIN = "INCOMPLETE"
NET_PROFITABILITY = "NOT_ESTABLISHED"
DISCORD_ACTIONABLE_PUBLICATION = "DISABLED"
PROMPT09_VERDICT = "NO_QUALIFIED_STRATEGY"

# Hard locks — configuration / env MUST NOT bypass these for actionable BUY/SELL
HARD_BLOCK_ACTIONABLE_DISCORD = True

# Operating modes
MODE_DISABLED = "DISABLED"
MODE_DRY_RUN = "DRY_RUN"
MODE_SHADOW = "SHADOW"
MODE_AUTHORIZED = "AUTHORIZED"
DEFAULT_MODE = MODE_SHADOW  # Prompt 6/10: must remain SHADOW or DRY_RUN

# Publication never auto-enabled
PUBLICATION_AUTHORIZATION_ENABLED = False

MODES = (MODE_DISABLED, MODE_DRY_RUN, MODE_SHADOW, MODE_AUTHORIZED)
