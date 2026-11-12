"""Phase 64.5 — Broker evidence ingestion & reconciliation foundation (READ-ONLY)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_5"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_5"
EXPORTS_DIR = DATA_ROOT / "exports" / "genuine"
FIXTURES_DIR = DATA_ROOT / "fixtures" / "simulated"
JOURNAL_ROOT = DATA_ROOT / "broker_evidence_journal"
# Also discover Phase63 genuine export directory (read-only reuse)
PHASE63_EXPORTS_DIR = SRC_DIR / "data" / "phase63" / "exports" / "genuine"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE64_1_REPORTS = PROJECT_ROOT / "reports" / "phase64_1"
PHASE64_2_REPORTS = PROJECT_ROOT / "reports" / "phase64_2"
PHASE64_3_REPORTS = PROJECT_ROOT / "reports" / "phase64_3"
PHASE64_4_REPORTS = PROJECT_ROOT / "reports" / "phase64_4"

RECIPE_ID = "phase64_5_broker_evidence_ingestion_reconciliation_v1"
SCHEMA_VERSION = "phase64_5_broker_evidence_v1"
PARSER_VERSION = "phase64_5_parser_v1"
RECON_VERSION = "phase64_5_recon_v1"
JOURNAL_SCHEMA_VERSION = "phase64_5_journal_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_READY = False
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
SIMULATED_LABEL = "SIMULATED_FIXTURE"

RECORD_KINDS = (
    "BROKER_ORDER",
    "BROKER_DEAL",
    "BROKER_POSITION",
    "BROKER_FEE",
    "BROKER_BALANCE_OPERATION",
)

LINKAGE_STATUSES = (
    "VERIFIED_LINK",
    "UNVERIFIED_CANDIDATE",
    "UNMATCHED_BROKER_RECORD",
    "CONFLICT",
    "UNMATCHED_AIBOT_INTENT",
)

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
)

UNKNOWN = "UNKNOWN"


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


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
