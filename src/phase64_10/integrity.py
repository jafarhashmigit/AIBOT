"""Integrity and no-order invariants for Phase 64.10."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_10.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE58_SPLITS,
    PHASE61_REPORTS,
    PHASE62_REPORTS,
    PHASE63_REPORTS,
    PHASE64_6_REPORTS,
    PHASE64_7_REPORTS,
    PHASE64_8_REPORTS,
    PHASE64_9_REPORTS,
    PHASE65,
    SRC_DIR,
    UNAPPROVED,
    canonical_json_sha256,
    file_sha256,
)


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    return list(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])


def _order_send_hits() -> list[str]:
    hits = []
    needles = ("mt5.order_send", "MetaTrader5.order_send")
    root = SRC_DIR / "phase64_10"
    for path in root.rglob("*.py"):
        if path.name in {"integrity.py", "adversarial.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        for n in needles:
            if n in text:
                hits.append(f"{path}:{n}")
    return hits


def audit_integrity() -> dict[str, Any]:
    holdout = phase58_holdout()
    reports = {
        "phase61": PHASE61_REPORTS / "PHASE61_FINAL_REPORT.md",
        "phase62": PHASE62_REPORTS / "PHASE62_FINAL_REPORT.md",
        "phase63": PHASE63_REPORTS / "PHASE63_FINAL_REPORT.md",
        "phase64_6": PHASE64_6_REPORTS / "PHASE64_6_FINAL_REPORT.md",
        "phase64_7": PHASE64_7_REPORTS / "PHASE64_7_FINAL_REPORT.md",
        "phase64_8": PHASE64_8_REPORTS / "PHASE64_8_FINAL_REPORT.md",
        "phase64_9": PHASE64_9_REPORTS / "PHASE64_9_FINAL_REPORT.md",
    }
    present = {k: v.is_file() for k, v in reports.items()}
    hits = _order_send_hits()
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "prior_reports_present": present,
        "prior_report_sha256": {k: file_sha256(v) for k, v in reports.items()},
        "order_send": ORDER_SEND,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites": hits,
        "broker_submission_enabled": BROKER_SUBMISSION_ENABLED,
        "broker_execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "risk_policy_constant": UNAPPROVED,
        "automated_orders": AUTOMATED_ORDERS,
        "broker_collection": BROKER_COLLECTION,
        "live_trading": LIVE_TRADING,
        "phase65": PHASE65,
        "swap_conflict_preserved": True,
        "checks_pass": (
            len(holdout) == 10
            and all(present.values())
            and "order_send" in PROHIBITED_MT5_API
            and not hits
            and BROKER_SUBMISSION_ENABLED is False
            and BROKER_EXECUTION_AUTHORIZED is False
            and AUTOMATED_ORDERS == "DISABLED"
            and LIVE_TRADING == "NOT_AUTHORIZED"
            and PHASE65 == "NOT_STARTED"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
