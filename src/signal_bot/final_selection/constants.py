"""Prompt 9 final candidate selection — no forced champion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SRC_DIR.parent
REPORTS = PROJECT_ROOT / "reports" / "completion"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
H70_STATUS = "FROZEN_UNVALIDATED_EXPLORATORY_NEGATIVE"
ORDER_SEND = "PROHIBITED"
BROKER_COLLECTION = "READ_ONLY"
LIVE_TRADING = "NOT_AUTHORIZED"
AUTOMATED_ORDERS = "DISABLED"
RISK_POLICY = "UNAPPROVED"
DISCORD_ACTIONABLE = "DISABLED"
EXECUTION_AUTHORIZATION = "BLOCKED"

VERDICT_QUALIFIED = "QUALIFIED_CANDIDATE_READY_FOR_FINAL_AUDIT"
VERDICT_NONE = "NO_QUALIFIED_STRATEGY"
VERDICT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
VERDICT_SAFETY = "SAFETY_INVARIANT_FAILURE"

ACTIVE_SYMBOL = "XAUUSDm"
ARCHIVE_SYMBOL = "XAUUSD"
COST_MODEL_VERSION = "prompt08_exness_xauusdm_cost_model_v1"

# Qualification floors (do not lower to force a winner)
MIN_INDEPENDENT_COMPLETE_LIVE_DATES = 20
MIN_REALIZED_TRADES = 40
MIN_DATE_BLOCKS = 10
MIN_NET_EXPECTANCY_R = 0.0  # must be > 0 under supported costs
REQUIRE_NET_ESTABLISHED = True


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))
