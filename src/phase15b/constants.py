"""Phase 15B frozen audit constants. Does not modify Phase 1–15A."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase15b"

RECIPE_ID = "phase15b_schema_compatibility_v1"
SEED = 42
TARGET_SCHEMA = "phase15a_signal_schema_v1"

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
HOLDOUT_NAME = "xauusd_m5_test.csv"

SOURCE_TYPE = "EXTERNAL_PROVIDER_SIGNAL"
FORBIDDEN_MERGE_SOURCES = (
    "HISTORICAL_HYPOTHETICAL",
    "AGENT_PAPER",
    "FORWARD_SHADOW",
)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
TELEGRAM_ACCESS_ATTEMPTS = 0
REAL_PROVIDER_MESSAGES_STORED = 0
BACKTESTS_EXECUTED = 0
MODEL_TRAINING_RUNS = 0
STAGE_B_AUTHORIZED = False
BUY_SELL_ENABLED = False

# Protected prior-phase artifacts (must remain unchanged)
PROTECTED_HASHES = {
    "src/phase14/run_phase14.py": "e20709522b032a49433e37eb76ff7adab60a54fa07630179238a2b790df55ec1",
    "src/phase14/strategy.py": "68db400ceae47495934b65e464e8f51a593611ef60b5438c09967b59bd76d69b",
    "src/phase14/decision.py": "4767905eda369a002af89d931f2acca38497d769931e3ae6f22b7d13e0a399dc",
    "docs/agent/PHASE_14_RESULTS.md": "66081d8f00511a5fb995464e291761aeb96c81fd30f5901f9e49e8d2fdb03e77",
    "docs/agent/PHASE_14_VALIDATION_PLAN.md": "183657da25d50529ef651ec7a59d9878982e67f2114497010dff9ace8dd5318f",
    "src/phase15a/schema.py": "29fb464e661a34edba85636700a2ebd1974de16116cf21963c70e6edb8aebede",
    "src/phase15a/constants.py": "d740675740756547c413a831eb78e1103e21959d791ae1199627c1cc1c01c477",
    "src/phase15a/run_phase15a.py": "8fae2ee7459bcd6ee498da8414a8b2e9c30e5100035bd45f2965c4542bc998f4",
    "docs/agent/PHASE_15A_PERMISSION_AND_FEASIBILITY.md": "a194eb173ba034f5556bce14663d2a00bd835b76f88dfba2d016076c9623b02c",
    "docs/agent/PHASE_15A_SIGNAL_SCHEMA.md": "7359cbd6dfa51e9344e6d6e590443c455f610aebdf8cecd6c1f358c3df9d4bc1",
}

SYNTHETIC_STYLE_IDS = (
    "vasilytrader_style",
    "anabelsignals_style",
)
