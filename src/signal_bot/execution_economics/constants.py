"""Prompt 8 execution economics constants — no production promotion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SRC_DIR.parent
REPORTS = PROJECT_ROOT / "reports" / "completion"
DATA_ROOT = SRC_DIR / "data" / "execution_economics"

COST_MODEL_VERSION = "prompt08_exness_xauusdm_cost_model_v1"
SENSITIVITY_VERSION = "prompt08_cost_sensitivity_v1"
SPREAD_ANALYSIS_VERSION = "prompt08_spread_analysis_v1"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H70_STATUS = "FROZEN_UNVALIDATED"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
ORDER_SEND = "PROHIBITED"
BROKER_COLLECTION = "READ_ONLY"
EXECUTION_AUTHORIZATION = "BLOCKED"
RISK_POLICY = "UNAPPROVED"
DISCORD_ACTIONABLE = "DISABLED"

ACTIVE_SYMBOL = "XAUUSDm"
SUPERSEDED_SYMBOL = "XAUUSD"
EXPECTED_SERVER = "Exness-MT5Trial15"
USER_TZ = "Asia/Karachi"
ASIA_TZ = "Asia/Tokyo"
LONDON_TZ = "Europe/London"

# Verified live symbol facts from Phase64.7 RO probe (account-specific snapshot)
VERIFIED_POINT = 0.001
VERIFIED_TICK_SIZE = 0.001
VERIFIED_TICK_VALUE = 0.1
VERIFIED_CONTRACT_SIZE = 100.0
VERIFIED_DIGITS = 3
VERIFIED_VOLUME_MIN = 0.01
VERIFIED_VOLUME_STEP = 0.01
VERIFIED_VOLUME_MAX = 200.0

# Evidence states
VERIFIED = "VERIFIED"
PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
UNKNOWN = "UNKNOWN"
CONFLICTED = "CONFLICTED"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN_FOR_EXECUTION = "UNKNOWN_FOR_EXECUTION"

# Verdicts
VERDICT_VERIFIED = "EXECUTION_ECONOMICS_VERIFIED"
VERDICT_PARTIAL = "EXECUTION_ECONOMICS_PARTIALLY_VERIFIED"
VERDICT_INSUFFICIENT = "INSUFFICIENT_BROKER_EVIDENCE"
VERDICT_COLLECTOR_FAIL = "COLLECTOR_RELIABILITY_FAILURE"
VERDICT_SAFETY = "SAFETY_INVARIANT_FAILURE"

TARGET_COMPLETE_LIVE_DATES = 20
STALE_QUOTE_MAX_AGE_SEC = 120.0
MAX_SPREAD_PRICE = 5.0  # absolute price-unit sanity for XAU

PHASE64_7_PROBE = PROJECT_ROOT / "reports" / "phase64_7" / "live_ro_probe_sanitized.json"
PHASE64_10_COMMISSION = PROJECT_ROOT / "reports" / "phase64_10" / "commission_evidence_report.json"
PHASE64_10_SWAP = PROJECT_ROOT / "reports" / "phase64_10" / "swap_conflict_analysis.json"
PHASE64_10_COST = PROJECT_ROOT / "reports" / "phase64_10" / "cost_model.json"
PROMPT07_FEASIBILITY = REPORTS / "PROMPT_07_DATA_FEASIBILITY.md"
PROMPT07_BUNDLE = REPORTS / "PROMPT_07_DISCOVERY_BUNDLE.json"

WINDOWS_TASK_NAME = "AIBOT_Phase67_Exness_RO_Collector"
WINDOWS_TASK_SCRIPT = PROJECT_ROOT / "scripts" / "install_collector_autostart.ps1"


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))
