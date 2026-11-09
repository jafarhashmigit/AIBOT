"""Phase 8 frozen conventions. Not a trading-rule search."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase8"

PHASE2_OOS_PATH = DATA_DIR / "phase2_oos_predictions.csv"
PHASE7_DECISIONS_PATH = DATA_DIR / "phase7_oos_agent_decisions.csv"
PHASE7_EVAL_PATH = DATA_DIR / "phase7_oos_agent_evaluation.csv"

PHASE2_OOS_SHA256 = "6ed9b1eff3664abe7a351b7e27674bc2f55abb55071afbf7c9ffa08c9dbbe54f"
RESEARCH_CUTOFF = "2026-09-29 18:50:00"
HOLDOUT_NAME = "xauusd_m5_test.csv"
SEED = 42
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
HORIZON_BARS = 12
BAR_MINUTES = 5
HORIZON_MINUTES = HORIZON_BARS * BAR_MINUTES
RECIPE_ID = "phase8_experience_memory_v1"

# Strict retrieval: outcome_end < decision_time. Equality is not visible.
BOUNDARY = "strict_lt"

FOLDS = ("WF1", "WF2", "WF3")
