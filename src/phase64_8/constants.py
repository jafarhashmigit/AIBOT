"""Phase 64.8 — Read-only broker evidence reconciliation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_8"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_8"
JOURNAL_ROOT = DATA_ROOT / "broker_evidence_journal"
LIVE_JOURNAL_ROOT = DATA_ROOT / "live_broker_evidence_journal"
FIXTURE_JOURNAL_ROOT = DATA_ROOT / "fixture_broker_evidence_journal"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE64_1_REPORTS = PROJECT_ROOT / "reports" / "phase64_1"
PHASE64_2_REPORTS = PROJECT_ROOT / "reports" / "phase64_2"
PHASE64_3_REPORTS = PROJECT_ROOT / "reports" / "phase64_3"
PHASE64_4_REPORTS = PROJECT_ROOT / "reports" / "phase64_4"
PHASE64_5_REPORTS = PROJECT_ROOT / "reports" / "phase64_5"
PHASE64_6_REPORTS = PROJECT_ROOT / "reports" / "phase64_6"
PHASE64_7_REPORTS = PROJECT_ROOT / "reports" / "phase64_7"

RECIPE_ID = "phase64_8_readonly_broker_evidence_reconciliation_v1"
COLLECTOR_VERSION = "phase64_8_ro_collector_v1"
RECON_VERSION = "phase64_8_recon_v1"
JOURNAL_SCHEMA_VERSION = "phase64_8_broker_evidence_journal_v1"
METADATA_VERSION = "phase64_8_account_metadata_v1"
APPROVAL_VERSION = "phase64_8_api_approval_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_READY = False
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"
UNAPPROVED = "UNAPPROVED"
ORDER_SEND = "PROHIBITED"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
UNKNOWN = "UNKNOWN"
SIMULATED_LABEL = "SIMULATED_FIXTURE"
EXPECTED_DEMO_LOGIN = 474906834
EXPECTED_SERVER = "Exness-MT5Trial15"

# Experience store labels — never merge
STORE_HISTORICAL_HYPOTHETICAL = "HISTORICAL_HYPOTHETICAL"
STORE_PAPER = "PAPER"
STORE_BROKER_EVIDENCE = "BROKER_EVIDENCE"

# Reconciliation states
STATE_UNKNOWN = "UNKNOWN"
STATE_OBSERVED = "OBSERVED"
STATE_RECONCILED = "RECONCILED"
STATE_ORPHAN_BROKER_EVIDENCE = "ORPHAN_BROKER_EVIDENCE"
STATE_MISSING_BROKER_EVIDENCE = "MISSING_BROKER_EVIDENCE"
STATE_CONFLICTING_BROKER_EVIDENCE = "CONFLICTING_BROKER_EVIDENCE"
STATE_DUPLICATE_BROKER_EVIDENCE = "DUPLICATE_BROKER_EVIDENCE"
STATE_UNRESOLVED = "UNRESOLVED"

RECON_STATES = (
    STATE_UNKNOWN,
    STATE_OBSERVED,
    STATE_RECONCILED,
    STATE_ORPHAN_BROKER_EVIDENCE,
    STATE_MISSING_BROKER_EVIDENCE,
    STATE_CONFLICTING_BROKER_EVIDENCE,
    STATE_DUPLICATE_BROKER_EVIDENCE,
    STATE_UNRESOLVED,
)

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
)

# Env vars that must never silently authorize trading
FORBIDDEN_AUTH_ENV = (
    "AIBOT_AUTHORIZE_TRADING",
    "AIBOT_LIVE_TRADING",
    "AIBOT_ORDER_SEND",
    "MT5_ALLOW_ORDER_SEND",
    "ENABLE_BROKER_ORDERS",
)

DEFAULT_HISTORY_LOOKBACK_DAYS = 30
API_TIMEOUT_SEC = 30

# MT5 deal type codes
DEAL_TYPE_BUY = 0
DEAL_TYPE_SELL = 1
DEAL_TYPE_BALANCE = 2
DEAL_TYPE_CREDIT = 3
DEAL_TYPE_CHARGE = 4
DEAL_TYPE_CORRECTION = 5
DEAL_TYPE_BONUS = 6
DEAL_TYPE_COMMISSION = 7

MUTATION_APIS_REMAIN_PROHIBITED = frozenset(
    {"order_send", "order_check", "buy", "sell", "Close", "symbol_select", "positions_total", "orders_total"}
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
