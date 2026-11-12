"""Phase 60 — execution reality & market coverage expansion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase60"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
PHASE59_REPORTS = PROJECT_ROOT / "reports" / "phase59"
PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"

RECIPE_ID = "phase60_execution_reality_market_coverage_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"
SYMBOL = "XAUUSD"

PKT = ZoneInfo("Asia/Karachi")
UTC = ZoneInfo("UTC")

# FX session windows in PKT hour (inclusive start, exclusive end) — labeled heuristic
SESSION_WINDOWS_PKT = {
    "ASIA": (5, 12),       # ~00:00–07:00 UTC
    "LONDON": (12, 17),    # ~07:00–12:00 UTC
    "NY": (17, 26),        # ~12:00–21:00 UTC (26 wraps via mod handling)
    "OFF_HOURS": (2, 5),   # late UTC evening / early PKT
}

BOOTSTRAP_SEED = 60_2026
BOOTSTRAP_N = 1000


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
