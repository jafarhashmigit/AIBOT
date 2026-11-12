"""Phase 64.3 — Hardened paper runtime adoption & operational validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase64_3"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase64_3"

PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE61_REPORTS = PROJECT_ROOT / "reports" / "phase61"
PHASE62_REPORTS = PROJECT_ROOT / "reports" / "phase62"
PHASE63_REPORTS = PROJECT_ROOT / "reports" / "phase63"
PHASE64_REPORTS = PROJECT_ROOT / "reports" / "phase64"
PHASE64_1_REPORTS = PROJECT_ROOT / "reports" / "phase64_1"
PHASE64_2_REPORTS = PROJECT_ROOT / "reports" / "phase64_2"

RECIPE_ID = "phase64_3_hardened_paper_runtime_adoption_v1"
HARDENING_VERSION = "phase64_2_hardened_v1"
APPROVED_ENGINE_CLASS = "HardenedLifecycleEngine"
APPROVED_FACTORY = "phase64_3.approved_runtime.make_approved_paper_engine"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
DEMO_COLLECTION = "READ_ONLY"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"


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
