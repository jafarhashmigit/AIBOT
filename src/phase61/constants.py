"""Phase 61 — Exness execution evidence & cost calibration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase61"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase61"
EVIDENCE_STORE = DATA_ROOT / "execution_evidence"
PHASE60_REPORTS = PROJECT_ROOT / "reports" / "phase60"
PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"

RECIPE_ID = "phase61_exness_execution_evidence_calibration_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"
INTENDED_INSTRUMENT = "XAUUSD"

# Official help URLs (investigation references — not automatic account config)
OFFICIAL_URLS = {
    "account_types": "https://get.exness.help/hc/en-us/articles/360013782240-Trading-account-types",
    "commodities": "https://get.exness.help/hc/en-us/articles/17854173039388-Commodities",
    "commission_fee": "https://get.exness.help/hc/en-us/articles/360012007919-Are-trading-accounts-charged-a-commission-fee",
    "account_suffixes": "https://get.exness.help/hc/en-us/articles/360014560220-Account-type-suffixes",
}

# Preregistered sufficiency thresholds (chosen before outcome analysis)
SUFFICIENCY_THRESHOLDS = {
    "min_independent_decisions": 200,
    "min_actual_fills": 200,
    "min_trading_days": 20,
    "min_sessions_represented": 3,
    "max_missing_record_rate": 0.10,
}


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
