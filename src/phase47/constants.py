"""Phase 47 constants — frozen before evaluation. Exploratory on exposed dates only."""

from __future__ import annotations

import hashlib
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase47"
DOCS_DIR = PROJECT_ROOT / "docs" / "agent"
DATA_OUT_DIR = SRC_DIR / "data" / "phase47"

PHASE46_OUTCOMES = SRC_DIR / "data" / "phase46" / "action_conditioned_outcomes.jsonl"
PHASE46_CONTRACT = PROJECT_ROOT / "reports" / "phase46" / "research_contract.json"
PHASE46_CONTRACT_SHA256_EXPECTED = (
    "44e33d0ea569c916d2f3332d875799076dc75149abe6b02f09abb4e44893984d"
)

RECIPE_ID = "phase47_calibrated_decision_intelligence_v1"
CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"

SYMBOL = "XAUUSD"
HORIZON_BARS = 12  # H12 overlap → purge/embargo within-day if needed
ATR_PERIOD = 14
PURGE_BARS = HORIZON_BARS  # outcomes overlapping horizon
EMBARGO_BARS = HORIZON_BARS

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

EXPECTED_N_OUTCOMES = 11211
EXPECTED_PER_ACTION = 3737

# --- Frozen decision thresholds (locked before evaluation; not tuned on validation) ---
POLICY_THRESHOLDS = {
    "ev_min_net_r": 0.0,  # require strictly greater after comparison
    "ev_strictly_positive": True,
    "stress_scenario_id": "STRESS_SPREAD_WIDEN_1_5X",
    "stress_ev_min_net_r": 0.0,
    "max_prediction_uncertainty": 0.45,  # |p-0.5|*2 inverted → uncertainty in [0,1]
    "min_market_familiarity": 0.05,  # reject if familiarity score < this
    "ood_distance_percentile": 0.95,  # train-distance cutoff
    "min_oof_samples_for_calibration_claim": 500,
    "max_ece_for_sufficient_calibration": 0.08,
    "note": "Frozen exploratory thresholds. Not optimized on Phase44 validation or holdout.",
}

# Walk-forward: train on first k dates, evaluate on date k (0-index eval starts at MIN_TRAIN_DATES)
MIN_TRAIN_DATES = 8

FEATURE_NAMES = [
    "ret_1",
    "ret_3",
    "ret_6",
    "ret_12",
    "atr_pct",
    "range_pct",
    "body_pct",
    "close_loc",
    "range_compression",
    "hour_sin",
    "hour_cos",
    "spread_pct",
    "realized_vol_12",
]

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
