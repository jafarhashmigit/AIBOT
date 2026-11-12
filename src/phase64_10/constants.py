"""Phase 64.10 — Broker economics, risk policy & execution readiness closure."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_10"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_10"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE64_9_REPORTS = PROJECT_ROOT / "reports" / "phase64_9"
PHASE64_8_REPORTS = PROJECT_ROOT / "reports" / "phase64_8"
PHASE64_7_REPORTS = PROJECT_ROOT / "reports" / "phase64_7"
PHASE64_6_REPORTS = PROJECT_ROOT / "reports" / "phase64_6"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"

RECIPE_ID = "phase64_10_broker_economics_risk_execution_readiness_v1"
COST_MODEL_VERSION = "phase64_10_cost_model_v1"
MARGIN_MODEL_VERSION = "phase64_10_margin_model_v1"
SESSION_MODEL_VERSION = "phase64_10_session_model_v1"
RISK_POLICY_VERSION = "phase64_10_demo_risk_policy_v1"
STRESS_VERSION = "phase64_10_cost_stress_v1"
SCORECARD_VERSION = "phase64_10_readiness_scorecard_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_READY = False
BROKER_EXECUTION_AUTHORIZED = False
BROKER_SUBMISSION_ENABLED = False
ORDER_SEND = "PROHIBITED"
UNAPPROVED = "UNAPPROVED"
PHASE65 = "NOT_STARTED"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
UNKNOWN = "UNKNOWN"

# Component evidence states
VERIFIED = "VERIFIED"
CONFLICTING = "CONFLICTING"
ESTIMATED = "ESTIMATED"
UNKNOWN_FOR_EXECUTION = "UNKNOWN_FOR_EXECUTION"

# Margin distinction
CALCULATED_ESTIMATE = "CALCULATED_ESTIMATE"
BROKER_OBSERVED = "BROKER_OBSERVED"

# Policy component statuses
APPROVED = "APPROVED"
PROPOSED = "PROPOSED"
BLOCKED_BY_UNKNOWN = "BLOCKED_BY_UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"
APPROVED_FOR_DEMO = "APPROVED_FOR_DEMO"

# Verified live facts (Phase64.7)
VERIFIED_TICK_SIZE = 0.001
VERIFIED_TICK_VALUE = 0.1
VERIFIED_CONTRACT_SIZE = 100.0
VERIFIED_DIGITS = 3
VERIFIED_CURRENCY = "USD"
VERIFIED_LEVERAGE = 2000
VERIFIED_SERVER = "Exness-MT5Trial15"
VERIFIED_VOLUME_MIN = 0.01
VERIFIED_VOLUME_STEP = 0.01
VERIFIED_VOLUME_MAX = 200.0
VERIFIED_DEMO_BALANCE = 500.0
EXPECTED_DEMO_LOGIN = 474906834

# Preserved swap conflict
SWAP_LONG_PHASE63 = -488.7
SWAP_LONG_PHASE64_7 = -644.8
SWAP_SHORT_LIVE = 0.0
SWAP_MODE_POINTS = 1
SWAP_ROLLOVER3DAYS = 3  # Wednesday

# Phase63 user-reported partial sessions / margin (not live API verified)
PHASE63_SESSIONS_PARTIAL = {
    "completeness": "PARTIAL",
    "provenance": "USER_REPORTED_PHASE63_ACTIVE_XAUUSDM_SPEC",
    "sunday": "23:01-24:00",
    "monday_to_thursday": {
        "segment_1": "00:00-21:58",
        "segment_2_start": "23:00",
        "segment_2_end": "TRUNCATED_UNKNOWN",
    },
    "friday": "00:00-21:58",
    "saturday": "CLOSED",
    "timezone": "UNKNOWN",
    "dst_behavior": "UNKNOWN",
    "missing_closing_times_invented": False,
}
PHASE63_MARGIN_BUY_USD_PER_LOT = 199.28  # user-reported; truncated rates

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
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
