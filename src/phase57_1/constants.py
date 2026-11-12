"""Phase 57.1 — durable experience recovery & transaction integrity."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase57_1"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase57_1"
STATE_DIR = DATA_ROOT / "state"
HIST_DIR = DATA_ROOT / "HISTORICAL_HYPOTHETICAL"
SHADOW_DIR = DATA_ROOT / "AGENT_SHADOW"
JOURNAL_DIR = DATA_ROOT / "journal"
WAL_DIR = JOURNAL_DIR / "wal"
QUARANTINE_DIR = JOURNAL_DIR / "quarantine"
CHECKPOINT_DIR = DATA_ROOT / "checkpoints"
AUDIT_DIR = DATA_ROOT / "audit"

RECIPE_ID = "phase57_1_durable_experience_recovery_transaction_integrity_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
JOURNAL_SCHEMA_VERSION = "phase57_1_journal_v1"
EXPECTED_NULL_POLICY = "phase54_null_policy_v1"

STAGES = (
    "POSITION_OPEN",
    "EXIT_DETECTED",
    "EXIT_COMMITTED",
    "OUTCOME_DERIVED",
    "EXPERIENCE_COMMITTED",
)

INJECT_STAGES = (
    "before_exit_detection",
    "after_exit_detection",
    "before_durable_exit_commit",
    "during_journal_write",
    "after_durable_exit_commit",
    "before_outcome_derivation",
    "during_outcome_persistence",
    "after_outcome_before_experience",
    "during_experience_reconstruction",
    "during_checkpoint_update",
    "during_restart_recovery",
)

BROKER_ORDERS = 0
MT5_LIVE = 0
AUTO_START = False


def canonical_json(obj: object) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def deterministic_experience_id(txn_id: str, source: str) -> str:
    return sha256_hex(f"phase57_1:exp:{txn_id}:{source}")


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))
