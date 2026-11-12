"""Phase 64.6 — Broker execution readiness engineering & MT5 read-only security review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_6"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_6"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE64_1_REPORTS = PROJECT_ROOT / "reports" / "phase64_1"
PHASE64_2_REPORTS = PROJECT_ROOT / "reports" / "phase64_2"
PHASE64_3_REPORTS = PROJECT_ROOT / "reports" / "phase64_3"
PHASE64_4_REPORTS = PROJECT_ROOT / "reports" / "phase64_4"
PHASE64_5_REPORTS = PROJECT_ROOT / "reports" / "phase64_5"

RECIPE_ID = "phase64_6_broker_execution_readiness_mt5_readonly_security_v1"
ADAPTER_VERSION = "phase64_6_readonly_metadata_adapter_v1"
CONTRACT_SPEC_VERSION = "phase64_6_xauusdm_contract_v1"
RISK_POLICY_VERSION = "phase64_6_demo_risk_policy_v1"
EXEC_GATE_VERSION = "phase64_6_execution_gate_v1"
METADATA_VERSION = "phase64_6_metadata_bundle_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_READY = False
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
UNKNOWN = "UNKNOWN"
INCOMPLETE = "INCOMPLETE"
UNAPPROVED = "UNAPPROVED"

FORBIDDEN_KEYS = frozenset(
    {"password", "investor_password", "api_secret", "api_token", "auth_token", "otp", "login_password"}
)

# APIs needed for full readiness vs current Phase12 posture
READINESS_API_NEEDS = (
    "account_info",
    "terminal_info",
    "symbol_info",
    "copy_rates_from_pos",  # freshness proxy when tick time available via symbol_info
    "positions_get",
    "orders_get",
    "history_orders_get",
    "history_deals_get",
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
