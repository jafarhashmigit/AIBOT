"""Prompt 10 final delivery constants — shadow bot; no strategy promotion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = SRC_DIR.parent
REPORTS = PROJECT_ROOT / "reports" / "completion"

# Four separate statuses
STATUS_ENGINEERING = "READ_ONLY_MONITORING_PATH_IMPLEMENTED"
STATUS_RUNTIME = "COLLECTOR_RUNTIME_VERIFIED_WHEN_RUNNING"
STATUS_QUANT = "NO_QUALIFIED_STRATEGY"
STATUS_LIVE_TRADING = "NOT_AUTHORIZED"

CHAMPION_STATUS = "NO_MODEL"
PRODUCTION_FINAL_ACTION = "WAIT"
STRATEGY_APPROVAL = "NOT_APPROVED"
LIVE_TRADING = "NOT_AUTHORIZED"
BROKER_COLLECTION = "READ_ONLY"
AUTOMATED_ORDERS = "DISABLED"
ORDER_SEND = "PROHIBITED"
EXECUTION_AUTHORIZATION = "BLOCKED"
RISK_POLICY = "UNAPPROVED"
COMMISSION = "UNKNOWN"
SWAP = "CONFLICTED_UNKNOWN_FOR_EXECUTION"
NET_PROFITABILITY = "NOT_ESTABLISHED"
DISCORD_ACTIONABLE = "DISABLED"
PROMPT09_VERDICT = "NO_QUALIFIED_STRATEGY"

# Hard lock: env/config flags MUST NOT unlock actionable Discord or order_send
HARD_BLOCK_ACTIONABLE_DISCORD = True
HARD_BLOCK_ORDER_SEND = True

VERDICT_DELIVERED = "OPERATIONAL_SHADOW_BOT_DELIVERED"
VERDICT_BLOCKERS = "ENGINEERING_DELIVERY_WITH_BLOCKERS"
VERDICT_SAFETY = "SAFETY_INVARIANT_FAILURE"

# Ops Discord: only SYSTEM_STATUS; requires explicit opt-in env (not actionable unlock)
ENV_OPS_STATUS_LIVE = "AIBOT_DISCORD_OPS_STATUS_LIVE"


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_sha256(obj: object) -> str:
    return sha256_hex(canonical_json(obj))
