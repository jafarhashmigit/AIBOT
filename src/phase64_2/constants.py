"""Phase 64.2 — Intent, identity & WAIT durability hardening (paper only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_2"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_2"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE64_1_REPORTS = PROJECT_ROOT / "reports" / "phase64_1"

RECIPE_ID = "phase64_2_intent_identity_wait_durability_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

# Extended terminal statuses (Phase64.2 journal subclass; Phase64 constants untouched)
STATUS_PAPER_FINALIZED = "PAPER_FINALIZED"
STATUS_WAIT_FINALIZED = "WAIT_FINALIZED"
STATUS_REPAIR_NEEDED = "REPAIR_NEEDED"

TERMINAL_STATUSES = frozenset(
    {
        STATUS_PAPER_FINALIZED,
        STATUS_WAIT_FINALIZED,
        "RISK_REJECTED",
        "NO_TRADE_WAIT",  # pre-experience terminal for non-trade; WAIT_FINALIZED after durable WAIT exp
        "CANCELLED",
        "EXPIRED",
        "BROKER_REJECTED",
        "MISSING_EXECUTION",
        "FILLED",
    }
)

OPEN_OK_PENDING = frozenset({"PENDING", "ORDER_LINKED", "PARTIAL_FILL", "UNFILLED"})

# Policy: one logical decision per M5 bar (day:idx)
DECISIONS_PER_BAR_POLICY = "ONE_LOGICAL_DECISION_PER_BAR"

CRASH_POINTS = (
    "after_durable_outcome_before_intent_status",
    "after_intent_outcome_before_experience_link",
    "during_wait_experience_append",
    "after_wait_experience_before_intent_finalize",
    "during_intent_status_repair",
)

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


def wait_experience_id(decision_id: str) -> str:
    return sha256_hex(f"phase64_2:wait_exp:{decision_id}")
