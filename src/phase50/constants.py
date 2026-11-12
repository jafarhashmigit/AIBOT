"""Phase 50 constants — causal experience learning experiment."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase50"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_DIR = SRC_DIR / "data" / "phase50"

RECIPE_ID = "phase50_adaptive_experience_learning_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

EXPERIENCE_SCHEMA_VERSION = "exp_v1"
POLICY_VERSION = "policy_v1"
LEARNER_VERSION = "shrink_bucket_v1"
MARKET_STATE_VERSION = "ctx_v1"

# Preregistered compact context (max buckets small)
SPREAD_ATR_EDGES = (0.05, 0.15)  # low / mid / high vs ATR
MIN_EXPERIENCE_PER_ACTION = 8
SHRINKAGE_K = 20.0  # pseudo-counts toward global mean
EV_MARGIN_OVER_WAIT = 0.0  # require Q(action) > WAIT (0) + margin
UNCERTAINTY_PENALTY = 0.25  # subtract penalty * stderr-like term

BOOTSTRAP_DRAWS = 800
BOOTSTRAP_SEED = 50
ALPHA = 0.05
N_POLICIES_COMPARED = 4  # Bonferroni across primary policies

# Forbidden dates
PHASE44_VALIDATION = frozenset(
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
