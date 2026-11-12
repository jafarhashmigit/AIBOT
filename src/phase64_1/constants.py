"""Phase 64.1 — Canonical decision & execution-intent integration (paper only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_1"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_1"
SNAPSHOT_DIR = DATA_ROOT / "market_snapshots"
INTENT_DIR = DATA_ROOT / "execution_intent"
STATE_DIR = DATA_ROOT / "state"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"

RECIPE_ID = "phase64_1_canonical_decision_execution_intent_integration_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

DECISION_ID_SCHEME = "phase64_1_canonical_v1"
SNAPSHOT_SCHEMA_VERSION = "phase64_1_market_snapshot_v1"
DOMAIN_AGENT_SHADOW = "AGENT_SHADOW"
DOMAIN_HISTORICAL = "HISTORICAL_HYPOTHETICAL"

CRASH_POINTS = (
    "after_snapshot_persistence",
    "after_decision_persistence",
    "after_risk_approval",
    "before_intent_persistence",
    "after_intent_before_paper_entry",
    "after_paper_entry",
    "after_exit_commit_before_outcome",
    "during_experience_reconstruction",
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
