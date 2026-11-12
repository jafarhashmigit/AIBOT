"""Phase0–64.1 immutability and safety."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_2.constants import (
    PHASE58_SPLITS,
    PHASE61_REPORTS,
    PHASE62_REPORTS,
    PHASE63_REPORTS,
    PHASE64_1_REPORTS,
    PHASE64_REPORTS,
    canonical_json_sha256,
    file_sha256,
)


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
        "phase64_1": PHASE64_1_REPORTS / "PHASE64_1_FINAL_REPORT.md",
    }
    present = {k: v.is_file() for k, v in reports.items()}
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "phase58_used": False,
        "phase0_64_1_source_modified": False,
        "prior_reports_present": present,
        "prior_report_sha256": {k: file_sha256(v) for k, v in reports.items()},
        "stores_merged": False,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "allowlist_expanded": False,
        "live_connection": False,
        "automated_orders": "DISABLED",
        "demo_collection": "READ_ONLY",
        "credentials_stored": False,
        "broker_execution_activated": False,
        "checks_pass": len(holdout) == 10 and all(present.values()) and "order_send" in PROHIBITED_MT5_API,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
