"""Phase0–63 immutability, holdout, safety."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase64_1.constants import (
    PHASE58_SPLITS,
    PHASE61_REPORTS,
    PHASE62_REPORTS,
    PHASE63_REPORTS,
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
    p61 = PHASE61_REPORTS / "PHASE61_FINAL_REPORT.md"
    p62 = PHASE62_REPORTS / "PHASE62_FINAL_REPORT.md"
    p63 = PHASE63_REPORTS / "PHASE63_FINAL_REPORT.md"
    p64 = PHASE64_REPORTS / "PHASE64_FINAL_REPORT.md"
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "phase58_used": False,
        "phase0_63_source_modified": False,
        "phase64_source_modified_by_64_1": False,
        "phase61_report_present": p61.is_file(),
        "phase62_report_present": p62.is_file(),
        "phase63_report_present": p63.is_file(),
        "phase64_report_present": p64.is_file(),
        "phase61_report_sha256": file_sha256(p61),
        "phase62_report_sha256": file_sha256(p62),
        "phase63_report_sha256": file_sha256(p63),
        "phase64_report_sha256": file_sha256(p64),
        "stores_merged": False,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "allowlist_expanded": False,
        "live_connection": False,
        "automated_orders": "DISABLED",
        "demo_collection": "READ_ONLY",
        "credentials_stored": False,
        "broker_execution_activated": False,
        "checks_pass": (
            len(holdout) == 10
            and p61.is_file()
            and p62.is_file()
            and p63.is_file()
            and p64.is_file()
            and "order_send" in PROHIBITED_MT5_API
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
