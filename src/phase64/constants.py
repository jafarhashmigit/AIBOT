"""Phase 64 — Demo decision-to-execution readiness audit (engineering only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64"
INTENT_DIR = DATA_ROOT / "execution_intent"
FIXTURE_DIR = DATA_ROOT / "fixtures"
LINKAGE_DIR = DATA_ROOT / "linkage"

# Read-only prior reports (never write)
PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"

RECIPE_ID = "phase64_demo_decision_execution_readiness_audit_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

JOURNAL_SCHEMA_VERSION = "phase64_execution_intent_journal_v1"

LIFECYCLE_STAGES = (
    "OBSERVATION",
    "MARKET_SNAPSHOT",
    "DECISION",
    "UNIQUE_DECISION_ID",
    "RISK_CHECK",
    "EXECUTION_INTENT",
    "FUTURE_BROKER_ORDER",
    "BROKER_DEAL",
    "PARTIAL_OR_FULL_FILL",
    "COMMISSION_FEES",
    "EXECUTION_OUTCOME",
    "EXPERIENCE",
)

INTENT_STATUSES = (
    "PENDING",
    "RISK_REJECTED",
    "NO_TRADE_WAIT",
    "CANCELLED",
    "EXPIRED",
    "UNFILLED",
    "ORDER_LINKED",
    "PARTIAL_FILL",
    "FILLED",
    "BROKER_REJECTED",
    "MISSING_EXECUTION",
)

JOURNAL_STAGES = (
    "DECISION_RECORDED",
    "INTENT_PERSISTED",
    "ORDER_LINKED",
    "DEAL_LINKED",
    "FILL_RECORDED",
    "OUTCOME_RECORDED",
    "EXPERIENCE_LINKED",
)

CRASH_POINTS = (
    "between_decision_and_intent",
    "after_intent_persistence",
    "during_order_link",
    "after_partial_fill",
    "during_deal_import_dedup",
)

# Phase 61/62/63 thresholds — do not lower
SUFFICIENCY_THRESHOLDS = {
    "min_independent_decisions": 200,
    "min_actual_fills": 200,
    "min_trading_days": 20,
    "min_sessions_represented": 3,
    "max_missing_record_rate": 0.10,
}

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
)

# Evidence labels — fixtures never count as genuine broker evidence
FIXTURE_PROVENANCE = "PHASE64_DETERMINISTIC_FIXTURE_NOT_GENUINE_BROKER_EVIDENCE"


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
