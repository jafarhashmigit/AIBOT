"""Phase 15A frozen audit constants."""

from __future__ import annotations

from pathlib import Path

from phase6.constants import CHAMPION_ID

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase15a"

RECIPE_ID = "phase15a_telegram_feasibility_v1"
SEED = 42
CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
HOLDOUT_NAME = "xauusd_m5_test.csv"

SOURCE_TYPE = "EXTERNAL_PROVIDER_SIGNAL"
# Must remain separate from existing AIBOT experience sources
FORBIDDEN_MERGE_SOURCES = (
    "HISTORICAL_HYPOTHETICAL",
    "AGENT_PAPER",
    "FORWARD_SHADOW",
)

PROVIDERS = (
    {
        "provider_id": "vasilytrader",
        "display_name": "VasilyTrader",
        "handle": "@vasilytrading",
        "tme_path": "vasilytrading",
    },
    {
        "provider_id": "anabelsignals",
        "display_name": "AnabelSignals",
        "handle": "@anabelsignals",
        "tme_path": "anabelsignals",
    },
    {
        "provider_id": "goldtradersunny",
        "display_name": "Gold Trader Sunny",
        "handle": "@goldtradersunny",
        "tme_path": "goldtradersunny",
    },
    {
        "provider_id": "fxpremiere",
        "display_name": "FX Premiere",
        "handle": "@forexsignalstrialgroup",
        "tme_path": "forexsignalstrialgroup",
    },
    {
        "provider_id": "unitedkings",
        "display_name": "United Kings",
        "handle": "@unitedkings1",
        "tme_path": "unitedkings1",
    },
)

TELEGRAM_TOS_URLS = (
    "https://telegram.org/tos/content-licensing",
    "https://core.telegram.org/api/terms",
    "https://telegram.org/tos/bot-developers",
    "https://core.telegram.org/bots/api",
)

MT5_CONNECTIONS = 0
BROKER_ORDERS = 0
TELEGRAM_SCRAPE_ATTEMPTS = 0
TELEGRAM_MESSAGES_STORED = 0
AI_ML_TRAINING_RUNS = 0
STAGE_B_AUTHORIZED = False
BUY_SELL_ENABLED = False

PHASE14_PROTECTED_HASHES = {
    "src/phase14/run_phase14.py": "e20709522b032a49433e37eb76ff7adab60a54fa07630179238a2b790df55ec1",
    "src/phase14/strategy.py": "68db400ceae47495934b65e464e8f51a593611ef60b5438c09967b59bd76d69b",
    "src/phase14/decision.py": "4767905eda369a002af89d931f2acca38497d769931e3ae6f22b7d13e0a399dc",
    "docs/agent/PHASE_14_RESULTS.md": "66081d8f00511a5fb995464e291761aeb96c81fd30f5901f9e49e8d2fdb03e77",
    "docs/agent/PHASE_14_VALIDATION_PLAN.md": "183657da25d50529ef651ec7a59d9878982e67f2114497010dff9ace8dd5318f",
}
