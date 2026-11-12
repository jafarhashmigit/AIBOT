"""Phase 64.4 — Broker demo execution safety design & authorization gate (DESIGN-ONLY)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_4"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_4"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE64_1_REPORTS = PROJECT_ROOT / "reports" / "phase64_1"
PHASE64_2_REPORTS = PROJECT_ROOT / "reports" / "phase64_2"
PHASE64_3_REPORTS = PROJECT_ROOT / "reports" / "phase64_3"

RECIPE_ID = "phase64_4_broker_demo_execution_safety_design_v1"
SCHEMA_VERSION = "phase64_4_broker_events_v1"
STATE_MACHINE_VERSION = "phase64_4_execution_fsm_v1"
AUTH_GATE_VERSION = "phase64_4_authorization_gate_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_READY = False
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
APPROVED_PAPER_FACTORY = "phase64_3.approved_runtime.make_approved_paper_engine"
HARDENING_VERSION = "phase64_2_hardened_v1"

# Design-only: no submission path exists in this phase
SUBMISSION_PATH_EXISTS = False
ORDER_SEND_REACHABLE = False

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
)

EVENT_TYPES = (
    "BROKER_EXECUTION_REQUEST",
    "BROKER_ORDER_SUBMISSION",
    "BROKER_ORDER_ACKNOWLEDGEMENT",
    "BROKER_DEAL",
    "BROKER_FILL",
    "BROKER_EXECUTION_REJECTION",
    "BROKER_EXECUTION_CANCELLATION",
    "BROKER_EXECUTION_RECONCILIATION",
)

EXECUTION_STATES = (
    "CREATED",
    "VALIDATED",
    "AUTHORIZED",
    "SUBMISSION_PENDING",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "REJECTED",
    "CANCELLED",
    "EXPIRED",
    "UNKNOWN_REQUIRES_RECONCILIATION",
    "BLOCKED_BY_RISK",
    "BLOCKED_BY_AUTHORIZATION",
)

TERMINAL_STATES = frozenset(
    {
        "FILLED",
        "REJECTED",
        "CANCELLED",
        "EXPIRED",
        "BLOCKED_BY_RISK",
        "BLOCKED_BY_AUTHORIZATION",
    }
)

# Risk keys — numerical limits MUST stay UNCONFIGURED until separately approved
RISK_LIMIT_KEYS = (
    "max_volume",
    "max_open_positions",
    "max_aggregate_exposure",
    "max_daily_loss",
    "max_drawdown",
    "max_spread",
    "max_spread_atr",
    "min_available_margin",
    "max_margin_utilization",
    "stale_market_data_max_age_ms",
    "trading_session_enforced",
    "symbol_spec_change_tolerance",
)

AUTH_GATES = (
    "demo_account_identity",
    "broker_server",
    "active_symbol",
    "complete_symbol_metadata",
    "complete_risk_configuration",
    "approved_execution_policy",
    "reconciliation_readiness",
    "durable_journal_readiness",
    "kill_switch_operational",
    "explicit_human_approval",
)


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
