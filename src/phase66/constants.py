"""Phase 66 constants — read-only market evidence; no order_send."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase66"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase66"
JOURNAL_ROOT = DATA_ROOT / "market_evidence_journal"
FIXTURE_JOURNAL_ROOT = DATA_ROOT / "fixture_market_evidence_journal"
WATERMARK_PATH = DATA_ROOT / "collection_watermark.json"
MANIFEST_PATH = DATA_ROOT / "dataset_manifest.json"
ELIGIBILITY_PATH = DATA_ROOT / "research_eligibility.json"
QUARANTINE_DIR = DATA_ROOT / "quarantine"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE65_REPORTS = PROJECT_ROOT / "reports" / "phase65"

RECIPE_ID = "phase66_market_evidence_collection_v1"
COLLECTOR_VERSION = "phase66_ro_market_collector_v2_prompt05"
SCHEMA_VERSION = "phase66_evidence_schema_v1"
DATASET_VERSION = "phase66_dataset_v1"

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
USER_TZ = "Asia/Karachi"
SERVER_TZ = "UTC"

# Evidence classes
BROKER_OBSERVED = "BROKER_OBSERVED"
HISTORICAL_ARCHIVE = "HISTORICAL_ARCHIVE"
DERIVED_OBSERVATION = "DERIVED_OBSERVATION"
HYPOTHETICAL_OUTCOME = "HYPOTHETICAL_OUTCOME"
PAPER_DECISION = "PAPER_DECISION"
PAPER_OUTCOME = "PAPER_OUTCOME"
EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"
SYNTHETIC_TEST_FIXTURE = "SYNTHETIC_TEST_FIXTURE"

EVIDENCE_CLASSES = (
    BROKER_OBSERVED,
    HISTORICAL_ARCHIVE,
    DERIVED_OBSERVATION,
    HYPOTHETICAL_OUTCOME,
    PAPER_DECISION,
    PAPER_OUTCOME,
    EXTERNAL_REFERENCE,
    SYNTHETIC_TEST_FIXTURE,
)

VERDICT_ENGINEERING = "COLLECTION_ENGINEERING_READY"
VERDICT_INSUFFICIENT = "INSUFFICIENT_INDEPENDENT_EVIDENCE"
VERDICT_QUALITY = "DATA_QUALITY_BLOCKED"
VERDICT_OPS = "COLLECTION_OPERATIONALLY_BLOCKED"

# Quality thresholds (engineering)
MAX_STALE_SEC = 120
MAX_SPREAD_POINTS = 5000  # abnormal guard for XAUUSDm (points)
MIN_PRICE = 100.0


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
