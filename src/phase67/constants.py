"""Phase 67 constants — read-only Exness collection; no order_send."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase67"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase67"
JOURNAL_ROOT = DATA_ROOT / "exness_market_evidence_journal"
FIXTURE_JOURNAL_ROOT = DATA_ROOT / "fixture_market_evidence_journal"
SERVICE_DIR = DATA_ROOT / "service"
PID_PATH = SERVICE_DIR / "collector.pid"
LOG_PATH = SERVICE_DIR / "collector.log"
STATE_PATH = SERVICE_DIR / "collector_state.json"
RUNTIME_MANIFEST = DATA_ROOT / "runtime_collection_manifest.json"
EXPLORATORY_DIR = DATA_ROOT / "exploratory"

RECIPE_ID = "phase67_exness_evidence_exploratory_v1"
COLLECTOR_VERSION = "phase67_exness_ro_collector_v2_prompt05"
SCHEMA_VERSION = "phase67_evidence_schema_v1"
DATASET_VERSION = "phase67_dataset_v1"
SERVICE_VERSION = "phase67_collector_service_v2_prompt05"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
BROKER_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_AUTHORIZED = False
BROKER_SUBMISSION_ENABLED = False
ORDER_SEND = "PROHIBITED"
EXECUTION_AUTHORIZATION = "BLOCKED"
UNAPPROVED = "UNAPPROVED"
COST_MODEL_INCOMPLETE = "INCOMPLETE"
COMMISSION_UNKNOWN = "UNKNOWN"
SWAP_UNKNOWN = "UNKNOWN_FOR_EXECUTION"
MARGIN_INCOMPLETE = "INCOMPLETE"
GENUINE_FILLS = "NONE_TRADE_FILLS"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
EXPECTED_DEMO_LOGIN = 474906834
EXPECTED_SERVER = "Exness-MT5Trial15"
BROKER_NAME = "Exness"
USER_TZ = "Asia/Karachi"

# Collection cadence
DEFAULT_INTERVAL_SEC = 30
DEFAULT_M5_LOOKBACK = 50
DEFAULT_VERIFY_RUNTIME_SEC = 90

# Exploratory fixed thresholds (NOT optimized for profit)
LOOKBACK_RANGE_BARS = 24
BREAKOUT_ATR_MULT = 0.5
REENTRY_BARS = 6
DISPLACEMENT_ATR_MULT = 1.5
VOL_HIGH_PCT = 0.67
VOL_LOW_PCT = 0.33
OUTCOME_HORIZONS = (1, 3, 6, 12)
EVENT_STRIDE = 12
ATR_PERIOD = 14

VERDICT_OPS_READY = "EXNESS_COLLECTION_OPERATIONALLY_READY"
VERDICT_EXPLORATORY = "EXPLORATORY_RESEARCH_COMPLETE"
VERDICT_INSUFFICIENT = "INSUFFICIENT_LIVE_EVIDENCE"
VERDICT_BLOCKED = "COLLECTION_BLOCKED"
VERDICT_INTEGRITY = "DATA_INTEGRITY_BLOCKED"


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
