"""Phase 64.7 — Live MT5 read-only probe & broker API security review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_7"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_7"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE64_6_REPORTS = PROJECT_ROOT / "reports" / "phase64_6"
PHASE64_5_REPORTS = PROJECT_ROOT / "reports" / "phase64_5"
PHASE64_4_REPORTS = PROJECT_ROOT / "reports" / "phase64_4"
PHASE64_3_REPORTS = PROJECT_ROOT / "reports" / "phase64_3"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE64_1_REPORTS = PROJECT_ROOT / "reports" / "phase64_1"
PHASE64_2_REPORTS = PROJECT_ROOT / "reports" / "phase64_2"

RECIPE_ID = "phase64_7_live_mt5_readonly_probe_api_security_review_v1"
PROBE_VERSION = "phase64_7_live_ro_probe_v1"
RECON_META_VERSION = "phase64_7_metadata_reconciliation_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_READY = False
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"
UNAPPROVED = "UNAPPROVED"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
UNKNOWN = "UNKNOWN"
INCOMPLETE = "INCOMPLETE"

# Expected demo identity from prior user-reported / Phase63 empty export (not a secret)
EXPECTED_DEMO_LOGIN = 474906834
EXPECTED_SERVER = "Exness-MT5Trial15"

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
)

# Critical fields for metadata completeness after live probe
CRITICAL_ACCOUNT_FIELDS = ("account_currency", "account_leverage", "server")
CRITICAL_SYMBOL_FIELDS = (
    "tick_size",
    "tick_value",
    "contract_size",
    "digits",
    "volume_min",
    "volume_step",
    "volume_max",
    "profit_currency",
    "margin_currency",
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
