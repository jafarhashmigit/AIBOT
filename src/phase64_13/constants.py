"""Phase 64.13 constants — CLOSE_ONLY semantics; no order_send."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_13"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = PROJECT_ROOT / "src" / "data" / "phase64_13"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE64_12_REPORTS = PROJECT_ROOT / "reports" / "phase64_12"
PHASE64_11_REPORTS = PROJECT_ROOT / "reports" / "phase64_11"
PHASE64_10_REPORTS = PROJECT_ROOT / "reports" / "phase64_10"
PHASE64_9_REPORTS = PROJECT_ROOT / "reports" / "phase64_9"
PHASE64_8_REPORTS = PROJECT_ROOT / "reports" / "phase64_8"
PHASE64_7_REPORTS = PROJECT_ROOT / "reports" / "phase64_7"
PHASE64_6_REPORTS = PROJECT_ROOT / "reports" / "phase64_6"

RECIPE_ID = "phase64_13_close_only_semantics_v1"
SESSION_SEMANTICS_VERSION = "phase64_13_session_semantics_v1"
SCHEDULE_VERSION = "exness_xauusdm_close_only_v1"
EVIDENCE_FREEZE_VERSION = "phase64_13_broker_evidence_freeze_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_AUTHORIZED = False
BROKER_SUBMISSION_ENABLED = False
ORDER_SEND = "PROHIBITED"
EXECUTION_AUTHORIZATION = "BLOCKED"
UNAPPROVED = "UNAPPROVED"
COST_MODEL_INCOMPLETE = "INCOMPLETE"
PHASE65 = "NOT_STARTED"
GENUINE_FILLS = "NONE_TRADE_FILLS"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SERVER_TZ = "UTC"
USER_TZ = "Asia/Karachi"

# Canonical session states — must not be collapsed
OPEN = "OPEN"
CLOSE_ONLY = "CLOSE_ONLY"
BREAK = "BREAK"
CLOSED = "CLOSED"
UNKNOWN = "UNKNOWN"

SESSION_STATES = (OPEN, CLOSE_ONLY, BREAK, CLOSED, UNKNOWN)

VERDICT_VALIDATED = "CLOSE_ONLY_SEMANTICS_VALIDATED"
VERDICT_PARTIAL = "CLOSE_ONLY_SEMANTICS_PARTIAL"
VERDICT_BLOCKED = "CLOSE_ONLY_SEMANTICS_BLOCKED"

# Documented Phase 64.12 defect
PHASE64_12_DEFECT = (
    "Phase 64.12 mapped published Close Only intervals to BREAK "
    "(schedule.py close_only_mapped_to=BREAK). CLOSE_ONLY was not an independent state."
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
