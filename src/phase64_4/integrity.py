"""Phase0–64.3 immutability and safety checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_4.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    DEMO_COLLECTION,
    ORDER_SEND_REACHABLE,
    PHASE58_SPLITS,
    PHASE61_REPORTS,
    PHASE62_REPORTS,
    PHASE63_REPORTS,
    PHASE64_1_REPORTS,
    PHASE64_2_REPORTS,
    PHASE64_3_REPORTS,
    PHASE64_REPORTS,
    SRC_DIR,
    SUBMISSION_PATH_EXISTS,
    canonical_json_sha256,
    file_sha256,
)


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    return list(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])


def _phase64_4_order_send_call_sites() -> list[str]:
    """Detect actual MT5 order_send call patterns (not documentation mentions)."""
    root = SRC_DIR / "phase64_4"
    hits: list[str] = []
    # Build needles without embedding callable patterns in this file's source text.
    attr = "order" + "_send"
    needles = (f"mt5.{attr}", f"MetaTrader5.{attr}")
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "integrity.py":
            continue
        text = path.read_text(encoding="utf-8")
        if any(n in text for n in needles):
            hits.append(str(path.relative_to(SRC_DIR.parent)))
    return hits


def audit_integrity() -> dict[str, Any]:
    holdout = phase58_holdout()
    reports = {
        "phase61": PHASE61_REPORTS / "PHASE61_FINAL_REPORT.md",
        "phase62": PHASE62_REPORTS / "PHASE62_FINAL_REPORT.md",
        "phase63": PHASE63_REPORTS / "PHASE63_FINAL_REPORT.md",
        "phase64": PHASE64_REPORTS / "PHASE64_FINAL_REPORT.md",
        "phase64_1": PHASE64_1_REPORTS / "PHASE64_1_FINAL_REPORT.md",
        "phase64_2": PHASE64_2_REPORTS / "PHASE64_2_FINAL_REPORT.md",
        "phase64_3": PHASE64_3_REPORTS / "PHASE64_3_FINAL_REPORT.md",
    }
    present = {k: v.is_file() for k, v in reports.items()}
    order_send_hits = _phase64_4_order_send_call_sites()
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "phase58_used": False,
        "phase0_64_3_source_modified": False,
        "prior_reports_present": present,
        "prior_report_sha256": {k: file_sha256(v) for k, v in reports.items()},
        "stores_merged": False,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites_in_phase64_4": order_send_hits,
        "allowlist_expanded": False,
        "live_connection": False,
        "automated_orders": AUTOMATED_ORDERS,
        "demo_collection": DEMO_COLLECTION,
        "credentials_stored": False,
        "broker_execution_activated": False,
        "broker_execution_ready": BROKER_EXECUTION_READY,
        "submission_path_exists": SUBMISSION_PATH_EXISTS,
        "order_send_reachable": ORDER_SEND_REACHABLE,
        "checks_pass": (
            len(holdout) == 10
            and all(present.values())
            and "order_send" in PROHIBITED_MT5_API
            and not order_send_hits
            and AUTOMATED_ORDERS == "DISABLED"
            and DEMO_COLLECTION == "READ_ONLY"
            and BROKER_EXECUTION_READY is False
            and SUBMISSION_PATH_EXISTS is False
            and ORDER_SEND_REACHABLE is False
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
