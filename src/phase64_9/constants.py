"""Phase 64.9 — Order submission security review & execution preflight (no live orders)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_9"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_9"
INTENT_ROOT = DATA_ROOT / "execution_intents"
FAKE_JOURNAL_ROOT = DATA_ROOT / "fake_broker_journal"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE64_8_REPORTS = PROJECT_ROOT / "reports" / "phase64_8"
PHASE64_7_REPORTS = PROJECT_ROOT / "reports" / "phase64_7"
PHASE64_6_REPORTS = PROJECT_ROOT / "reports" / "phase64_6"
PHASE64_5_REPORTS = PROJECT_ROOT / "reports" / "phase64_5"
PHASE64_4_REPORTS = PROJECT_ROOT / "reports" / "phase64_4"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"

RECIPE_ID = "phase64_9_order_submission_security_execution_preflight_v1"
PREFLIGHT_VERSION = "phase64_9_execution_preflight_v1"
INTENT_FSM_VERSION = "phase64_9_intent_fsm_v1"
ADAPTER_VERSION = "phase64_9_broker_execution_adapter_v1"
AUTH_MODEL_VERSION = "phase64_9_authorization_model_v1"
RISK_CALC_VERSION = "phase64_9_risk_calc_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_READY = False
BROKER_EXECUTION_AUTHORIZED = False
# Hard safety — NOT env/config toggleable. Changing this requires source change + Phase65+.
BROKER_SUBMISSION_ENABLED = False
ORDER_SEND = "PROHIBITED"
UNAPPROVED = "UNAPPROVED"
PHASE65 = "NOT_STARTED"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
UNKNOWN = "UNKNOWN"
RISK_INCOMPLETE = "RISK_INCOMPLETE"
PREFLIGHT_REJECTED = "PREFLIGHT_REJECTED"
SIMULATED_LABEL = "SIMULATED_FIXTURE"

EXPECTED_DEMO_LOGIN = 474906834
EXPECTED_SERVER = "Exness-MT5Trial15"
EXPECTED_CURRENCY = "USD"

# Live verified contract facts (Phase64.7) — not interchangeable with unresolved costs
VERIFIED_TICK_SIZE = 0.001
VERIFIED_TICK_VALUE = 0.1
VERIFIED_CONTRACT_SIZE = 100.0
VERIFIED_DIGITS = 3
VERIFIED_LEVERAGE = 2000

# Preserved swap conflict (do not overwrite / interchange)
SWAP_LONG_PHASE63 = -488.7
SWAP_LONG_PHASE64_7 = -644.8

# Intent states (Phase64.9 hardened)
INTENT_CREATED = "INTENT_CREATED"
PREFLIGHT_REJECTED_STATE = "PREFLIGHT_REJECTED"
SUBMISSION_PENDING = "SUBMISSION_PENDING"
SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
BROKER_ACCEPTED = "BROKER_ACCEPTED"
BROKER_REJECTED = "BROKER_REJECTED"
RECONCILIATION_PENDING = "RECONCILIATION_PENDING"
RECONCILED = "RECONCILED"

INTENT_STATES = (
    INTENT_CREATED,
    PREFLIGHT_REJECTED_STATE,
    SUBMISSION_PENDING,
    SUBMISSION_UNKNOWN,
    BROKER_ACCEPTED,
    BROKER_REJECTED,
    RECONCILIATION_PENDING,
    RECONCILED,
)

# Authorization modes (mutually exclusive progression; current = RO)
MODE_RESEARCH = "research_mode"
MODE_PAPER = "paper_mode"
MODE_BROKER_RO = "broker_read_only_mode"
MODE_BROKER_PREPARED = "broker_execution_prepared"
MODE_BROKER_AUTHORIZED = "broker_execution_authorized"
MODE_EMERGENCY = "emergency_shutdown"

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
)

FORBIDDEN_AUTH_ENV = (
    "AIBOT_AUTHORIZE_TRADING",
    "AIBOT_LIVE_TRADING",
    "AIBOT_ORDER_SEND",
    "MT5_ALLOW_ORDER_SEND",
    "ENABLE_BROKER_ORDERS",
    "BROKER_SUBMISSION_ENABLED",
    "AIBOT_BROKER_EXECUTION_AUTHORIZED",
)

STORE_HISTORICAL = "HISTORICAL_HYPOTHETICAL"
STORE_PAPER = "PAPER"
STORE_BROKER_EVIDENCE = "BROKER_EVIDENCE"
STORE_BROKER_EXECUTION = "BROKER_EXECUTION_EXPERIENCE"
STORE_SYNTHETIC = "SYNTHETIC_FIXTURE"


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
