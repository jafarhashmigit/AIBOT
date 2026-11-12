"""Phase 57 — independent reliability & execution integrity validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase57"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase57"
STATE_DIR = DATA_ROOT / "state"
HIST_DIR = DATA_ROOT / "HISTORICAL_HYPOTHETICAL"
SHADOW_DIR = DATA_ROOT / "AGENT_SHADOW"
CHECKPOINT_DIR = DATA_ROOT / "checkpoints"
CRASH_DIR = DATA_ROOT / "crash_stages"

RECIPE_ID = "phase57_autonomous_reliability_execution_integrity_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

ARCHIVE_ROOT = SRC_DIR / "data" / "phase53" / "mt5" / "raw"

# Critical invariants — all required for VALIDATED
CRITICAL_INVARIANTS = (
    "once_per_accepted_observation",
    "no_duplicate_candle_decisions",
    "sl_tp_before_horizon_in_trace",
    "buy_exit_bid_sell_exit_ask",
    "sl_first_same_bar",
    "no_double_close",
    "no_orphaned_opens_after_clean_run",
    "unsafe_data_blocks_entry",
    "null_policy_default",
    "experience_stores_separated",
    "restart_no_duplicate_entry",
    "independent_recompute_match",
)

BROKER_ORDERS = 0
MT5_LIVE = 0
AUTO_START = False
GIT_COMMIT = False
GIT_PUSH = False


def canonical_json_sha256(obj: object) -> str:
    import json

    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
