"""Phase 6 protocol versions. Frozen; not a trading-rule search."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SRC_DIR.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "phase6"

RESEARCH_CUTOFF = "2026-09-29 18:50:00"
HOLDOUT_NAME = "xauusd_m5_test.csv"
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
SEED = 42

OBSERVATION_VERSION = "phase6_observation_v1"
FEATURE_VERSION_REF = "m5_utc_corrected_allowlist_v1"
DECISION_ENGINE_VERSION = "phase6_conservative_ev_v1"
RISK_GATE_VERSION = "phase6_wait_only_no_champion_v1"
COST_ASSUMPTION_VERSION = "label_m5_spread_floor_15pts_c005_v1"
JOURNAL_SCHEMA_VERSION = "phase6-1.0"
REGISTRY_SCHEMA_VERSION = "phase6-1.0"
PROTOCOL_ID = "phase6_oos_signal_protocol_v1"

# Reused from Phase 3 frozen policy. Not retuned here.
CONSERVATIVE_K = 1.0
EV_TAU = 0.0
EV_MIN_GAP = 0.02

# Architecture G example: floored spread as a fraction of SL distance.
MAX_COST_TO_SL_FRACTION = 0.15

CHAMPION_ID = "no_model"
ALLOW_PRODUCTION = False
