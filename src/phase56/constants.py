"""Phase 56 — autonomous observer & lifecycle integration."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase56"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_ROOT = SRC_DIR / "data" / "phase56"
STATE_DIR = DATA_ROOT / "state"
HIST_DIR = DATA_ROOT / "HISTORICAL_HYPOTHETICAL"
SHADOW_DIR = DATA_ROOT / "AGENT_SHADOW"
CHECKPOINT_DIR = DATA_ROOT / "checkpoints"

RECIPE_ID = "phase56_autonomous_observer_lifecycle_integration_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
AGENT_VERSION = "phase56_integrated_agent_v1"
POLICY_VERSION = "phase54_null_policy_v1"  # production default remains NullPolicy

ARCHIVE_ROOT = SRC_DIR / "data" / "phase53" / "mt5" / "raw"
HORIZON_BARS = 12

DEFAULT_POLL = {
    "max_iterations": 500,
    "max_wall_seconds": 120,
    "poll_interval_seconds": 0.0,  # historical replay: no sleep by default
    "max_candles": 200,
    "checkpoint_every": 10,
    "max_observation_age_seconds": 900,
}

BROKER_ORDERS = 0
MT5_LIVE_CONNECTIONS = 0
PACKAGES_INSTALLED = False
GIT_COMMIT = False
GIT_PUSH = False
AUTO_START = False


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
