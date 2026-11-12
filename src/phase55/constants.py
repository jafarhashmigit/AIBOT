"""Phase 55 — end-to-end paper execution verification (engineering only)."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase55"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase55"
STATE_DIR = DATA_ROOT / "state"
TEST_HIST_DIR = DATA_ROOT / "ENGINEERING_TEST" / "HISTORICAL_HYPOTHETICAL"
TEST_SHADOW_DIR = DATA_ROOT / "ENGINEERING_TEST" / "AGENT_SHADOW"
TEST_LEDGER_DIR = DATA_ROOT / "ENGINEERING_TEST" / "ledger"

RECIPE_ID = "phase55_end_to_end_paper_execution_verification_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
ENGINEERING_POLICY_VERSION = "phase55_engineering_test_policy_v1"
ENGINEERING_TAG = "ENGINEERING_TEST_ONLY"

# Production Phase54 roots — read-only for isolation proof
PHASE54_HIST = SRC_DIR / "data" / "phase54" / "HISTORICAL_HYPOTHETICAL"
PHASE54_SHADOW = SRC_DIR / "data" / "phase54" / "AGENT_SHADOW"
PHASE54_POLICY = "phase54_null_policy_v1"

ARCHIVE_ROOT = SRC_DIR / "data" / "phase53" / "mt5" / "raw"
HORIZON_BARS = 12

BROKER_ORDERS = 0
MT5_LIVE_CONNECTIONS = 0
PACKAGES_INSTALLED = False
GIT_COMMIT = False
GIT_PUSH = False


def canonical_json_sha256(obj: object) -> str:
    import json

    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
