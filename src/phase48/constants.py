"""Phase 48 constants — forensic audit only. No strategy discovery."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase48"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"

PHASE46_OUTCOMES = SRC_DIR / "data" / "phase46" / "action_conditioned_outcomes.jsonl"
PHASE46_CONTRACT = PROJECT_ROOT / "reports" / "phase46" / "research_contract.json"
PHASE46_CONTRACT_SHA256_EXPECTED = (
    "44e33d0ea569c916d2f3332d875799076dc75149abe6b02f09abb4e44893984d"
)
PHASE47_VERDICT = PROJECT_ROOT / "reports" / "phase47" / "final_verdict.json"
PHASE47_POLICY_DECISIONS = SRC_DIR / "data" / "phase47" / "policy_decisions_oof.jsonl"

RECIPE_ID = "phase48_decision_intelligence_root_cause_audit_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

EXPECTED_N = 11211
EXPECTED_PER_ACTION = 3737

ENGINEERING_DATES = [
    "2025-07-02",
    "2025-07-09",
    "2025-07-16",
    "2025-07-23",
    "2025-07-30",
    "2025-08-06",
    "2025-08-20",
    "2025-08-27",
    "2025-09-04",
    "2025-09-11",
    "2025-09-18",
    "2025-09-24",
    "2025-10-07",
    "2025-10-14",
    "2025-10-20",
]

FORBIDDEN_VALIDATION_DATES = frozenset(
    {
        "2025-10-27",
        "2025-10-31",
        "2025-11-10",
        "2025-11-17",
        "2025-11-21",
        "2025-12-04",
        "2025-12-11",
        "2025-12-17",
        "2025-12-24",
        "2025-12-31",
        "2026-01-07",
        "2026-01-20",
        "2026-01-27",
        "2026-02-03",
        "2026-02-10",
    }
)

BROKER_ORDERS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
HOLDOUT_ACCESSES = 0
GIT_COMMIT = False
GIT_PUSH = False
MT5_CONNECTIONS = 0


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_sha256(obj: object) -> str:
    import json

    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
