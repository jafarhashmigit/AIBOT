"""Phase 45 constants — audit only."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase45"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
REPORTS_ROOT = PROJECT_ROOT / "reports"

RECIPE_ID = "phase45_research_architecture_audit_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

# Locked from prior phases — do not reopen for discovery
PHASE44_VALIDATION_DATES_LOCKED = [
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
]

RETIRED_STRATEGIES = ("H13_C", "mean_reversion")
PHASE42_REJECTED_PREFIX = "H42_"
PHASE44_REJECTED_PREFIX = "H44_"

BROKER_ORDERS = 0
DISCORD_MESSAGES_SENT = 0
TELEGRAM_MESSAGES_SENT = 0
PACKAGES_INSTALLED = False
HOLDOUT_ACCESSES = 0
GIT_COMMIT = False
GIT_PUSH = False
MT5_CONNECTIONS = 0
