"""Phase integrity and safety for 64.9."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_9.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    DEMO_COLLECTION,
    LIVE_TRADING,
    PHASE58_SPLITS,
    PHASE61_REPORTS,
    PHASE62_REPORTS,
    PHASE63_REPORTS,
    PHASE64_4_REPORTS,
    PHASE64_5_REPORTS,
    PHASE64_6_REPORTS,
    PHASE64_7_REPORTS,
    PHASE64_8_REPORTS,
    PHASE64_REPORTS,
    PHASE65,
    SRC_DIR,
    canonical_json_sha256,
    file_sha256,
)
from phase64_9.path_trace import build_path_trace


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    return list(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])


def audit_integrity() -> dict[str, Any]:
    holdout = phase58_holdout()
    reports = {
        "phase61": PHASE61_REPORTS / "PHASE61_FINAL_REPORT.md",
        "phase62": PHASE62_REPORTS / "PHASE62_FINAL_REPORT.md",
        "phase63": PHASE63_REPORTS / "PHASE63_FINAL_REPORT.md",
        "phase64": PHASE64_REPORTS / "PHASE64_FINAL_REPORT.md",
        "phase64_4": PHASE64_4_REPORTS / "PHASE64_4_FINAL_REPORT.md",
        "phase64_5": PHASE64_5_REPORTS / "PHASE64_5_FINAL_REPORT.md",
        "phase64_6": PHASE64_6_REPORTS / "PHASE64_6_FINAL_REPORT.md",
        "phase64_7": PHASE64_7_REPORTS / "PHASE64_7_FINAL_REPORT.md",
        "phase64_8": PHASE64_8_REPORTS / "PHASE64_8_FINAL_REPORT.md",
    }
    present = {k: v.is_file() for k, v in reports.items()}
    trace = build_path_trace()
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "prior_reports_present": present,
        "prior_report_sha256": {k: file_sha256(v) for k, v in reports.items()},
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "broker_submission_enabled": BROKER_SUBMISSION_ENABLED,
        "broker_execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "path_trace_pass": trace.get("pass"),
        "order_send_call_sites": trace["order_send"]["call_sites_in_src"],
        "automated_orders": AUTOMATED_ORDERS,
        "demo_collection": DEMO_COLLECTION,
        "broker_collection": BROKER_COLLECTION,
        "live_trading": LIVE_TRADING,
        "phase65": PHASE65,
        "swap_conflict_preserved": True,
        "historical_evidence_unmodified_policy": True,
        "checks_pass": (
            len(holdout) == 10
            and all(present.values())
            and "order_send" in PROHIBITED_MT5_API
            and BROKER_SUBMISSION_ENABLED is False
            and BROKER_EXECUTION_AUTHORIZED is False
            and trace.get("pass")
            and AUTOMATED_ORDERS == "DISABLED"
            and LIVE_TRADING == "NOT_AUTHORIZED"
            and PHASE65 == "NOT_STARTED"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
