"""Integrity checks for Phase 67."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase67.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    SRC_DIR,
    canonical_json_sha256,
)


def audit_integrity() -> dict[str, Any]:
    splits = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
    holdout = []
    if splits.is_file():
        holdout = list(json.loads(splits.read_text(encoding="utf-8")).get("holdout_sealed") or [])
    hits = []
    _os = "order" + "_send"
    for path in (SRC_DIR / "phase67").rglob("*.py"):
        if path.name in {"integrity.py", "security.py", "adversarial.py", "tick_api_audit.py"}:
            continue
        text = path.read_text(encoding="utf-8")
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
