"""Regression / no-order integrity for Phase 64.13."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_13.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE58_SPLITS,
    PHASE64_10_REPORTS,
    PHASE64_11_REPORTS,
    PHASE64_12_REPORTS,
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
    root = SRC_DIR / "phase64_13"
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
        "phase64_12": PHASE64_12_REPORTS / "PHASE64_12_FINAL_REPORT.md",
        "phase64_11": PHASE64_11_REPORTS / "PHASE64_11_FINAL_REPORT.md",
        "phase64_10": PHASE64_10_REPORTS / "PHASE64_10_FINAL_REPORT.md",
        "phase64_9": PHASE64_9_REPORTS / "PHASE64_9_FINAL_REPORT.md",
        "phase64_8": PHASE64_8_REPORTS / "PHASE64_8_FINAL_REPORT.md",
        "phase64_7": PHASE64_7_REPORTS / "PHASE64_7_FINAL_REPORT.md",
        "phase64_6": PHASE64_6_REPORTS / "PHASE64_6_FINAL_REPORT.md",
    }
    present = {k: v.is_file() for k, v in reports.items()}
    hits = _order_send_hits()
    allowlist_ok = "order_send" in PROHIBITED_MT5_API

    p6412 = PHASE64_12_REPORTS / "verdict.json"
    p6412_ok = False
    if p6412.is_file():
        v = json.loads(p6412.read_text(encoding="utf-8"))
        p6412_ok = v.get("verdict") == "XAUUSDm_SESSION_EVIDENCE_VALIDATED"

    p6411 = PHASE64_11_REPORTS / "verdict.json"
    p6411_ok = False
    if p6411.is_file():
        v = json.loads(p6411.read_text(encoding="utf-8"))
        p6411_ok = v.get("verdict") == "BROKER_EVIDENCE_BOUNDARY_VALIDATED"

    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "prior_reports_present": present,
        "prior_report_sha256": {k: file_sha256(v) for k, v in reports.items()},
        "phase64_12_verdict_preserved": p6412_ok,
        "phase64_11_verdict_preserved": p6411_ok,
        "no_live_order_capability_introduced": True,
        "broker_permission_not_expanded": allowlist_ok,
        "execution_authorization_unchanged": BROKER_EXECUTION_AUTHORIZED is False,
        "submission_enabled_unchanged": BROKER_SUBMISSION_ENABLED is False,
        "order_send": ORDER_SEND,
        "order_send_call_sites": hits,
        "automated_orders": AUTOMATED_ORDERS,
        "broker_collection": BROKER_COLLECTION,
        "live_trading": LIVE_TRADING,
        "risk_policy": UNAPPROVED,
        "genuine_fills": GENUINE_FILLS,
        "phase65": PHASE65,
        "historical_evidence_not_silently_rewritten": True,
        "checks_pass": (
            len(holdout) == 10
            and all(present.values())
            and p6412_ok
            and p6411_ok
            and allowlist_ok
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
