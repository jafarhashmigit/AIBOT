"""Phase 15C frozen constants. Does not modify Phase 1–15B."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase15c"

RECIPE_ID = "phase15c_permission_readiness_v1"
REGISTRY_VERSION = "permission_registry_v1"
IMPORT_CONTRACT_VERSION = "provider_export_import_contract_v1"
SEED = 42
TARGET_SIGNAL_SCHEMA = "phase15a_signal_schema_v1"

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
HOLDOUT_NAME = "xauusd_m5_test.csv"

SOURCE_TYPE = "EXTERNAL_PROVIDER_SIGNAL"
FORBIDDEN_MERGE_SOURCES = (
    "HISTORICAL_HYPOTHETICAL",
    "AGENT_PAPER",
    "FORWARD_SHADOW",
)

PERMISSION_STATUSES = (
    "NOT_REQUESTED",
    "REQUESTED",
    "PARTIALLY_GRANTED",
    "GRANTED",
    "REJECTED",
    "EXPIRED",
    "REVOKED",
)

PERMISSION_SCOPES = (
    "historical_message_access",
    "signal_storage",
    "backtesting_evaluation",
    "data_retention",
    "ai_ml_training",
)

PROVIDERS = (
    {
        "provider_id": "vasilytrader",
        "display_name": "VasilyTrader",
        "handle": "@vasilytrading",
    },
    {
        "provider_id": "anabelsignals",
        "display_name": "AnabelSignals",
        "handle": "@anabelsignals",
    },
    {
        "provider_id": "goldtradersunny",
        "display_name": "Gold Trader Sunny",
        "handle": "@goldtradersunny",
    },
    {
        "provider_id": "fxpremiere",
        "display_name": "FX Premiere",
        "handle": "@forexsignalstrialgroup",
    },
    {
        "provider_id": "unitedkings",
        "display_name": "United Kings",
        "handle": "@unitedkings1",
    },
)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
TELEGRAM_CONNECTIONS = 0
PROVIDER_MESSAGES_SENT = 0
EXTERNAL_DATA_COLLECTED = 0
PAID_SUBSCRIPTIONS = 0
HOLDOUT_ACCESSES = 0
MODEL_TRAINING_RUNS = 0
STAGE_B_AUTHORIZED = False
BUY_SELL_ENABLED = False

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
    "src/phase15b/constants.py": "bb8ce4217abcab8afea774e79fe1ac265f95f2f8c034aee23b409be2cda7aaa8",
    "src/phase15b/mappers.py": "7c37ed673458a1450de5e3e2d910fea6b8e1554fda43c4ffc1cf234f74892525",
    "src/phase15b/run_phase15b.py": "d4150c5608152bd282f1f16c96009d4b1743be6bc194535654858abae0b021bd",
    "docs/agent/PHASE_15B_SCHEMA_COMPATIBILITY.md": "2a5266a149af5faaf71a40bda476221472a986e3760786e025b446e99ab6a8bf",
    "docs/agent/PHASE_15B_FIELD_MAPPING.md": "b370d412f54c9b19d39157df28aa58e7855bf463bd0aa9f0ce46933e7f843051",
}
