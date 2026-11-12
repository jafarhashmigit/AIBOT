"""Phase 64.11 — Broker economics evidence closure & unknown-boundary validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_11"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE64_10_REPORTS = PROJECT_ROOT / "reports" / "phase64_10"
PHASE64_9_REPORTS = PROJECT_ROOT / "reports" / "phase64_9"
PHASE64_8_REPORTS = PROJECT_ROOT / "reports" / "phase64_8"
PHASE64_7_REPORTS = PROJECT_ROOT / "reports" / "phase64_7"
PHASE64_6_REPORTS = PROJECT_ROOT / "reports" / "phase64_6"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"

RECIPE_ID = "phase64_11_broker_economics_evidence_boundary_v1"
BOUNDARY_VERSION = "phase64_11_evidence_boundary_v1"
INVENTORY_VERSION = "phase64_11_evidence_inventory_v1"
TAXONOMY_VERSION = "phase64_11_cost_taxonomy_v1"
POLICY_EVIDENCE_VERSION = "phase64_11_risk_policy_evidence_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_AUTHORIZED = False
BROKER_SUBMISSION_ENABLED = False
ORDER_SEND = "PROHIBITED"
UNAPPROVED = "UNAPPROVED"
PHASE65 = "NOT_STARTED"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"
GENUINE_FILLS = "NONE_TRADE_FILLS"

ACTIVE_SYMBOL = "XAUUSDm"
UNKNOWN = "UNKNOWN"
UNKNOWN_FOR_EXECUTION = "UNKNOWN_FOR_EXECUTION"

# Evidence type tags
LIVE_ACCOUNT = "LIVE_ACCOUNT"
BROKER_DOCUMENTATION = "BROKER_DOCUMENTATION"
CALCULATED = "CALCULATED"
ESTIMATED = "ESTIMATED"
SYNTHETIC_TEST = "SYNTHETIC_TEST"
USER_REPORTED = "USER_REPORTED"

# Boundary classifications (exactly one per blocker)
CLOSABLE_FROM_EXISTING_EVIDENCE = "CLOSABLE_FROM_EXISTING_EVIDENCE"
CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE = "CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE"
REQUIRES_GENUINE_ACCOUNT_EVENT = "REQUIRES_GENUINE_ACCOUNT_EVENT"
STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT = "STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT"
ALREADY_VALIDATED = "ALREADY_VALIDATED"

BOUNDARY_CLASSES = (
    CLOSABLE_FROM_EXISTING_EVIDENCE,
    CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE,
    REQUIRES_GENUINE_ACCOUNT_EVENT,
    STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT,
    ALREADY_VALIDATED,
)

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

SWAP_LONG_PHASE63 = -488.7
SWAP_LONG_PHASE64_7 = -644.8
SWAP_SHORT_LIVE = 0.0
SWAP_MODE_POINTS = 1
SWAP_ROLLOVER3DAYS = 3

# Live account stop-out (observed Phase64.11 probe)
LIVE_MARGIN_SO_CALL = 60.0
LIVE_MARGIN_SO_SO = 0.0
LIVE_MARGIN_MODE = 2  # retail hedging


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
