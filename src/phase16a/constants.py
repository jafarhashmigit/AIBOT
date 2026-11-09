"""Phase 16A constants. Does not modify Phase 1–15C."""

from __future__ import annotations

from pathlib import Path

from phase5.constants import MT5_TERMINAL
from phase6.constants import CHAMPION_ID, RESEARCH_CUTOFF
from phase14.constants import (
    CANDIDATE_ID,
    PRIMARY_PULLBACK_Q_HIGH,
    PRIMARY_PULLBACK_Q_LOW,
    SPREAD_FLOOR_USD,
)

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data" / "phase16a"
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase16a"

RECIPE_ID = "phase16a_h13c_shadow_pilot_v1"
SEED = 42
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
HORIZON_BARS = 12
BAR_MINUTES = 5
HORIZON_MINUTES = HORIZON_BARS * BAR_MINUTES
SOURCE_TYPE = "FORWARD_SHADOW"
SERVER_TZ = "Europe/Athens"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

CHAMPION = CHAMPION_ID
CHAMPION_STATUS = "NO_MODEL"
CANDIDATE = CANDIDATE_ID  # H13_C_H1_PULLBACK
CANDIDATE_STATUS = "EXPERIMENTAL"
CANDIDATE_PHASE14_STATUS = "RETAINED_EXPERIMENTAL"

SESSION_DURATION_SECONDS = 3600  # controlled 1-hour pilot
POLL_INTERVAL_SECONDS = 15
HOLDOUT_NAME = "xauusd_m5_test.csv"
RESEARCH_CUTOFF_UTC = RESEARCH_CUTOFF

# Frozen Phase 14 WF3 train cuts (q25/q75). Not re-optimized.
FROZEN_CUTS = {
    "q_low": PRIMARY_PULLBACK_Q_LOW,
    "q_high": PRIMARY_PULLBACK_Q_HIGH,
    "close_ema_low": -0.0010069324198160867,
    "close_ema_high": 0.0009989244530461683,
    "n_train": 36061,
    "train_cutoff": "2026-08-26 12:55:00",
    "source": "phase14_replication.json:cuts_independent.WF3",
}
SPREAD_FLOOR = SPREAD_FLOOR_USD
MT5_TERMINAL_PATH = MT5_TERMINAL

STAGE_B_LIVE_ORDERS = False
BUY_SELL_PRODUCTION_ENABLED = False
MODEL_TRAINING_RUNS = 0
PARAMETER_OPTIMIZATION_RUNS = 0
HOLDOUT_ACCESSES = 0
BROKER_ORDERS = 0
BACKGROUND_SERVICES = 0
SCHEDULED_TASKS = 0
GITHUB_PUSH = False

PROTECTED_HASHES = {
    "src/phase14/strategy.py": "68db400ceae47495934b65e464e8f51a593611ef60b5438c09967b59bd76d69b",
    "src/phase14/decision.py": "4767905eda369a002af89d931f2acca38497d769931e3ae6f22b7d13e0a399dc",
    "src/phase14/h1_trend.py": "76fbf7fbd2335e97c9275f0dc8ae4f3678d90b59a16e729c0ebbb4cb51930c68",
    "src/phase14/run_phase14.py": "e20709522b032a49433e37eb76ff7adab60a54fa07630179238a2b790df55ec1",
    "docs/agent/PHASE_14_RESULTS.md": "66081d8f00511a5fb995464e291761aeb96c81fd30f5901f9e49e8d2fdb03e77",
    "docs/agent/PHASE_14_VALIDATION_PLAN.md": "183657da25d50529ef651ec7a59d9878982e67f2114497010dff9ace8dd5318f",
    "src/phase12/mt5_readonly.py": "f5ae87c8f9832be8fdfd9a58a753a2fe3261a0637524630eeeb215b887bec3ca",
    "src/phase12/mt5_allowlist.py": "e3bd0c6ad3a08b8ac2f8f7b744cda6bc8d2b2fd9262c6081ba9247a3a50cf6ba",
    "src/phase12/outcome_observer.py": "be52ed4aa8a2f5285a2fa232782eecb2695227b1b1c11a54c41fe770f022c59e",
    "src/phase12/bar_validator.py": "6d883ba3959305ada3246df8b1f1c7f2d8aab3bb74c2ca3a64b23a2208da5e69",
    "src/phase12/session_manager.py": "7534e0ad8214957078925ce0f75f54e3960da76e7bfc0e3ff7ebbf2571aa12ca",
    "src/phase12c/gate_adapter.py": "c0b6f20cf8de5b6d3d0096a3627c76a1f134a9890a042cc65bc30c67ad8db1c3",
    "src/phase12c/constants.py": "bf621d782504ceae1d853901835e1607c67833811a5fa467a9da2891b4f8f156",
    "src/phase15c/constants.py": "a41245f26e32f4b7a05648b3391a3997c91e1b95ec2b5aadd53d0ccfbde75838",
    "src/phase6/risk_gate.py": "a9ffbe3429a0800a23e8a1ffee6af5602e7e29e73a612e477c8f6105507df9d3",
}
