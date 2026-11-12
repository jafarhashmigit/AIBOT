"""Phase 64.12 constants — session evidence only; no order_send."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_12"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = PROJECT_ROOT / "src" / "data" / "phase64_12"
SESSION_JOURNAL_ROOT = DATA_ROOT / "session_evidence_journal"
SOURCE_SNAPSHOT_DIR = DATA_ROOT / "source_snapshots"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE64_11_REPORTS = PROJECT_ROOT / "reports" / "phase64_11"
PHASE64_10_REPORTS = PROJECT_ROOT / "reports" / "phase64_10"
PHASE64_9_REPORTS = PROJECT_ROOT / "reports" / "phase64_9"
PHASE64_8_REPORTS = PROJECT_ROOT / "reports" / "phase64_8"
PHASE64_7_REPORTS = PROJECT_ROOT / "reports" / "phase64_7"
PHASE64_6_REPORTS = PROJECT_ROOT / "reports" / "phase64_6"

RECIPE_ID = "phase64_12_xauusdm_session_evidence_v1"
SCHEDULE_VERSION = "exness_xauusd_us_dst_winter_2026_11_01_v1"
SESSION_MODEL_VERSION = "phase64_12_session_model_v1"
FRESHNESS_POLICY_VERSION = "phase64_12_freshness_v1"

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
COST_MODEL_INCOMPLETE = "INCOMPLETE"
PHASE65 = "NOT_STARTED"
GENUINE_FILLS = "NONE_TRADE_FILLS"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
BASE_INSTRUMENT = "XAUUSD"
ACCOUNT_TYPE = "Standard"
PLATFORM = "MT5"
SERVER_TZ = "UTC"
USER_TZ = "Asia/Karachi"

# Session states
OPEN = "OPEN"
CLOSED = "CLOSED"
BREAK = "BREAK"
UNKNOWN = "UNKNOWN"

# Evidence kinds
BROKER_PUBLISHED_SESSION = "BROKER_PUBLISHED_SESSION"
ACCOUNT_TERMINAL_OBSERVED_SESSION = "ACCOUNT_TERMINAL_OBSERVED_SESSION"
INFERRED_SESSION = "INFERRED_SESSION"
UNKNOWN_SESSION = "UNKNOWN_SESSION"

# Verdicts
VERDICT_VALIDATED = "XAUUSDm_SESSION_EVIDENCE_VALIDATED"
VERDICT_PARTIAL = "XAUUSDm_SESSION_EVIDENCE_PARTIAL"
VERDICT_BLOCKED = "XAUUSDm_SESSION_EVIDENCE_BLOCKED"

# Freshness
MAX_EVIDENCE_AGE_DAYS = 180
DST_WINTER_EFFECTIVE = "2026-11-01"
NEXT_US_DST_START = "2027-03-14"  # second Sunday in March 2027

# Official source URLs (Exness Help Center)
SRC_TRADING_HOURS = "https://get.exness.help/hc/en-us/articles/4405235684498-Instrument-trading-hours"
SRC_DST_UPDATE = (
    "https://get.exness.help/hc/en-us/articles/31342732737180-"
    "Trading-Hours-Update-End-of-US-Daylight-Saving-Time-01-Nov-2026"
)
SRC_MT_TIMEZONE = "https://get.exness.help/hc/en-us/articles/360014390760-What-is-the-default-timezone-set-for-MetaTrader"
SRC_SUFFIXES = "https://get.exness.help/hc/en-us/articles/360014560220-Account-type-suffixes"
SRC_COMMODITIES = "https://get.exness.help/hc/en-us/articles/17854173039388-Commodities"
SRC_STANDARD = "https://get.exness.help/hc/en-us/articles/17537782738460-Standard-account"

RETRIEVAL_DATE = "2026-11-12"


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
