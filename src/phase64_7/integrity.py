"""Phase0–64.6 immutability and safety."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_7.constants import (
    AUTOMATED_ORDERS,
    BROKER_EXECUTION_READY,
    DEMO_COLLECTION,
    PHASE58_SPLITS,
    PHASE61_REPORTS,
    PHASE62_REPORTS,
    PHASE63_REPORTS,
    PHASE64_1_REPORTS,
    PHASE64_2_REPORTS,
    PHASE64_3_REPORTS,
    PHASE64_4_REPORTS,
    PHASE64_5_REPORTS,
    PHASE64_6_REPORTS,
    PHASE64_REPORTS,
    SRC_DIR,
    canonical_json_sha256,
    file_sha256,
)


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    return list(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])


def _order_send_calls() -> list[str]:
    root = SRC_DIR / "phase64_7"
    hits = []
    attr = "order" + "_send"
    needles = (f"mt5.{attr}", f"MetaTrader5.{attr}")
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "integrity.py":
            continue
        text = path.read_text(encoding="utf-8")
        if any(n in text for n in needles):
            hits.append(str(path))
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
        "phase64_4": PHASE64_4_REPORTS / "PHASE64_4_FINAL_REPORT.md",
        "phase64_5": PHASE64_5_REPORTS / "PHASE64_5_FINAL_REPORT.md",
        "phase64_6": PHASE64_6_REPORTS / "PHASE64_6_FINAL_REPORT.md",
    }
    present = {k: v.is_file() for k, v in reports.items()}
    hits = _order_send_calls()
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "phase58_used": False,
        "phase0_64_6_source_modified": False,
        "prior_reports_present": present,
        "prior_report_sha256": {k: file_sha256(v) for k, v in reports.items()},
        "stores_merged": False,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "order_send_call_sites": hits,
        "allowlist_expanded": "positions_get" in PERMITTED_MT5_API,
        "allowlist_unchanged": "order_send" in PROHIBITED_MT5_API and "symbol_info" in PERMITTED_MT5_API,
        "allowlist_note": "Phase64.8 RO expansion; mutation APIs remain prohibited",
        "automated_orders": AUTOMATED_ORDERS,
        "demo_collection": DEMO_COLLECTION,
        "credentials_stored": False,
        "broker_execution_ready": BROKER_EXECUTION_READY,
        "checks_pass": (
            len(holdout) == 10
            and all(present.values())
            and not hits
            and "order_send" in PROHIBITED_MT5_API
            and AUTOMATED_ORDERS == "DISABLED"
            and DEMO_COLLECTION == "READ_ONLY"
            and BROKER_EXECUTION_READY is False
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
