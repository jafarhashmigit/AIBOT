"""Phase 65 constants — research-only; Champion remains NO_MODEL."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase65"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase65"
REGISTRY_PATH = DATA_ROOT / "hypothesis_registry_frozen.json"
CONSUMPTION_PATH = DATA_ROOT / "consumption_registry.json"

RECIPE_ID = "phase65_independent_edge_discovery_v1"
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
GENUINE_FILLS = "NONE_TRADE_FILLS"
PHASE65_STARTED = True  # this phase
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

SYMBOL_RESEARCH = "XAUUSD"  # archive symbol
SYMBOL_LIVE = "XAUUSDm"
HORIZON_BARS = 12
EVENT_STRIDE = 12
ATR_PERIOD = 14
MIN_ATR = 1e-8

HYPOTHESIS_BUDGET = 3
BONFERRONI_N = 3
ALPHA = 0.05
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 65
MIN_POLICY_TRADES = 15  # small unconsumed pool; still require minimum

N_DISCOVERY = 7
N_VALIDATION = 4

VERDICT_PENDING = "NEW_EDGE_DISCOVERED_VALIDATION_PENDING"
VERDICT_VALIDATED = "INDEPENDENT_EDGE_VALIDATED_RESEARCH_ONLY"
VERDICT_NONE = "NO_NEW_INFORMATION_FAMILY_FOUND"
VERDICT_INCONCLUSIVE = "RESEARCH_INCONCLUSIVE"
VERDICT_BLOCKED = "RESEARCH_BLOCKED"

# Inherit Phase58 do-not-repeat + H58 IDs
from phase58.constants import DO_NOT_REPEAT as _P58_DNR

DO_NOT_REPEAT = tuple(_P58_DNR) + (
    "H58_P1_PRIOR_SESSION_LOCATION",
    "H58_W1_COSTLY_SPREAD_WAIT",
    "H58_I1_INACTIVITY_WAIT",
    "shrink_bucket_v1",
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
