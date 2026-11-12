"""Phase 58 — autonomous market intelligence & decision quality research."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase58"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase58"
STATE_DIR = DATA_ROOT / "state"
EVENTS_DIR = DATA_ROOT / "events"
EXPERIENCE_DIR = DATA_ROOT / "experience"

RECIPE_ID = "phase58_autonomous_market_intelligence_research_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
HORIZON_BARS = 12
EVENT_STRIDE = 12
ATR_PERIOD = 14
MIN_ATR = 1e-8

ARCHIVE_ROOTS = (
    SRC_DIR / "data" / "phase53" / "mt5" / "raw",
    SRC_DIR / "data" / "phase49" / "mt5" / "raw",
    SRC_DIR / "data" / "phase43" / "mt5" / "raw",
)

N_DISCOVERY = 20
N_VALIDATION = 10
N_HOLDOUT = 10  # untouched final test — only opened if discovery+validation survivors
BONFERRONI_N = 3
ALPHA = 0.05
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 58
MIN_POLICY_TRADES = 20

DO_NOT_REPEAT = (
    "H13_C",
    "mean_reversion",
    "H42_A",
    "H42_B",
    "H42_C",
    "H42_D",
    "H42_E",
    "H42_F",
    "H42_G",
    "H42_H",
    "H42_I",
    "H42_J",
    "H44_1",
    "H44_2",
    "H44_3",
    "H44_4",
    "H44_5",
    "H_A1",
    "H_A2",
    "H_A3",
    "H_B1",
    "H_B2",
    "H_B3",
    "H_C1",
    "H_C2",
    "H_C3",
    "H_D1",
    "H_D2",
    "H_D3",
    "H_E1",
    "H_E2",
    "H_E3",
    "H_F1",
    "H_F2",
    "H_F3",
    "F1_CMC",
    "F2_EXF",
    "F3_SLF",
    "shrink_bucket_v1",
    "phase47_13feat_overlapping",
)


def canonical_json(obj: object) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))
