"""Phase 59 — market data quality & execution economics intelligence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase59"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase59"

RECIPE_ID = "phase59_market_data_execution_economics_intelligence_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"
SYMBOL = "XAUUSD"

ARCHIVE_ROOTS = (
    ("phase38", SRC_DIR / "data" / "phase38" / "mt5" / "raw"),
    ("phase40", SRC_DIR / "data" / "phase40" / "mt5" / "raw"),
    ("phase43", SRC_DIR / "data" / "phase43" / "mt5" / "raw"),
    ("phase49", SRC_DIR / "data" / "phase49" / "mt5" / "raw"),
    ("phase53", SRC_DIR / "data" / "phase53" / "mt5" / "raw"),
)

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"

# Sessions in UTC (approximate FX session windows for research labeling)
SESSION_WINDOWS = {
    "ASIA": (0, 7),
    "LONDON": (7, 12),
    "NY": (12, 21),
    "OFF_HOURS": (21, 24),
}

ATR_PERIOD = 14


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))
