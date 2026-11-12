"""Security / champion / no-order integrity for Phase 65."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase65.constants import (
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
    UNAPPROVED,
    canonical_json_sha256,
    file_sha256,
)


def audit_integrity() -> dict[str, Any]:
    splits = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
    holdout = []
    if splits.is_file():
        holdout = list(json.loads(splits.read_text(encoding="utf-8")).get("holdout_sealed") or [])

    hits = []
    for path in (SRC_DIR / "phase65").rglob("*.py"):
        if path.name in {"integrity.py", "adversarial.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        for n in ("mt5.order_send", "MetaTrader5.order_send"):
            if n in text:
                hits.append(f"{path}:{n}")

    out = {
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "live": LIVE_TRADING,
        "automated_orders": AUTOMATED_ORDERS,
        "order_send": ORDER_SEND,
        "order_send_in_prohibited": "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites": hits,
        "broker_collection": BROKER_COLLECTION,
        "submission_enabled": BROKER_SUBMISSION_ENABLED,
        "execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "risk_policy": UNAPPROVED,
        "genuine_fills": GENUINE_FILLS,
        "phase58_holdout_n": len(holdout),
        "phase58_splits_sha256": file_sha256(splits),
        "checks_pass": (
            CHAMPION_STATUS == "NO_MODEL"
            and PRODUCTION_FINAL_ACTION == "WAIT"
            and LIVE_TRADING == "NOT_AUTHORIZED"
            and AUTOMATED_ORDERS == "DISABLED"
            and ORDER_SEND == "PROHIBITED"
            and "order_send" in PROHIBITED_MT5_API
            and not hits
            and BROKER_SUBMISSION_ENABLED is False
            and BROKER_EXECUTION_AUTHORIZED is False
            and len(holdout) == 10
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
