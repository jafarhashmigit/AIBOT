"""Integrity checks for Phase 66."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase66.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE58_SPLITS,
    PRODUCTION_FINAL_ACTION,
    SRC_DIR,
    UNAPPROVED,
    canonical_json_sha256,
)


def audit_integrity() -> dict[str, Any]:
    holdout = []
    if PHASE58_SPLITS.is_file():
        holdout = list(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])
    hits = []
    for path in (SRC_DIR / "phase66").rglob("*.py"):
        if path.name in {"integrity.py", "adversarial.py", "security.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        _os = "order" + "_send"
        for n in (f"mt5.{_os}", f"MetaTrader5.{_os}"):
            if n in text:
                hits.append(f"{path}:{n}")
    out = {
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "live": LIVE_TRADING,
        "automated_orders": AUTOMATED_ORDERS,
        "order_send": ORDER_SEND,
        "order_send_call_sites": hits,
        "broker_collection": BROKER_COLLECTION,
        "submission": BROKER_SUBMISSION_ENABLED,
        "execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "risk_policy": UNAPPROVED,
        "genuine_fills": GENUINE_FILLS,
        "phase58_holdout_n": len(holdout),
        "checks_pass": (
            CHAMPION_STATUS == "NO_MODEL"
            and PRODUCTION_FINAL_ACTION == "WAIT"
            and not hits
            and "order_send" in PROHIBITED_MT5_API
            and BROKER_SUBMISSION_ENABLED is False
            and BROKER_EXECUTION_AUTHORIZED is False
            and len(holdout) == 10
            and LIVE_TRADING == "NOT_AUTHORIZED"
            and AUTOMATED_ORDERS == "DISABLED"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
