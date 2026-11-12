"""Phase 68 constants — research only; no order_send."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase68"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase68"

RECIPE_ID = "phase68_displacement_response_live_integrity_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
BROKER_COLLECTION = "READ_ONLY"
BROKER_EXECUTION_AUTHORIZED = False
BROKER_SUBMISSION_ENABLED = False
ORDER_SEND = "PROHIBITED"
EXECUTION_AUTHORIZATION = "BLOCKED"
UNAPPROVED = "UNAPPROVED"
COST_MODEL_INCOMPLETE = "INCOMPLETE"
COMMISSION_UNKNOWN = "UNKNOWN"
SWAP_UNKNOWN = "UNKNOWN_FOR_EXECUTION"
GENUINE_FILLS = "NONE_TRADE_FILLS"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

# Fixed displacement definition (Phase67 — do not optimize)
ATR_PERIOD = 14
DISPLACEMENT_ATR_MULT = 1.5
EVENT_STRIDE = 12
OUTCOME_HORIZONS = (1, 3, 6, 12, 24)
VOL_LOW_PCT = 0.33
VOL_HIGH_PCT = 0.67
# Warmup bars before first eligible event index (match Phase67: ATR + lookback range)
LOOKBACK_RANGE_BARS = 24
EXCURSION_THRESHOLD_ATR = 0.5  # time-to-threshold
FLAT_ATR = 0.25  # no meaningful directional movement at horizon

PHASE67_JOURNAL = SRC_DIR / "data" / "phase67" / "exness_market_evidence_journal"
PHASE67_VERIFY = PROJECT_ROOT / "reports" / "phase67" / "verify_runtime.json"
PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"

BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 68

VERDICT_BEHAVIOUR = "EXPLORATORY_BEHAVIOUR_IDENTIFIED"
VERDICT_INSUFFICIENT = "INSUFFICIENT_SAMPLE"
VERDICT_LIVE_OK = "LIVE_COLLECTION_INTEGRITY_VERIFIED"
VERDICT_LIVE_FAIL = "LIVE_COLLECTION_INTEGRITY_FAILED"


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))
