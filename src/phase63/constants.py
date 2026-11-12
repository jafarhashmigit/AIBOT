"""Phase 63 — Exness demo execution evidence integration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase63"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase63"
META_DIR = DATA_ROOT / "account_metadata"
EXPORTS_DIR = DATA_ROOT / "exports" / "genuine"
SCHEMA_SAMPLES_DIR = DATA_ROOT / "export_schema_samples"
# Phase63-owned store (do not write into Phase62 intake — preserves Phase62 test isolation)
STORE_ROOT = DATA_ROOT / "exness_demo_execution"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE62_INTAKE_DIR = SRC_DIR / "data" / "phase62" / "intake"
PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"

RECIPE_ID = "phase63_exness_demo_execution_evidence_integration_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"
VERIFICATION_STATUS = "USER_REPORTED_FROM_CONNECTED_MT5_SPECIFICATION"

# Phase 61/62 thresholds — do not lower
SUFFICIENCY_THRESHOLDS = {
    "min_independent_decisions": 200,
    "min_actual_fills": 200,
    "min_trading_days": 20,
    "min_sessions_represented": 3,
    "max_missing_record_rate": 0.10,
}

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
