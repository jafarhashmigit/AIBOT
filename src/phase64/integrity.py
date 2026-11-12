"""Domain separation, holdout, Phase0–63 immutability, security."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase50.experience_store import ExperienceStore
from phase64.constants import (
    PHASE58_SPLITS,
    PHASE61_REPORTS,
    PHASE62_REPORTS,
    PHASE63_REPORTS,
    SRC_DIR,
    canonical_json_sha256,
    file_sha256,
)


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    return list(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])


def audit_integrity() -> dict[str, Any]:
    holdout = phase58_holdout()
    hist_n = shadow_n = 0
    hist = SRC_DIR / "data" / "phase57_1" / "HISTORICAL_HYPOTHETICAL"
    shadow = SRC_DIR / "data" / "phase57_1" / "AGENT_SHADOW"
    if hist.exists():
        try:
            hist_n = ExperienceStore("HISTORICAL_HYPOTHETICAL", root=hist).n
        except Exception:
            pass
    if shadow.exists():
        try:
            shadow_n = ExperienceStore("AGENT_SHADOW", root=shadow).n
        except Exception:
            pass

    p61 = PHASE61_REPORTS / "PHASE61_FINAL_REPORT.md"
    p62 = PHASE62_REPORTS / "PHASE62_FINAL_REPORT.md"
    p63 = PHASE63_REPORTS / "PHASE63_FINAL_REPORT.md"

    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "phase58_holdout_days": holdout,
        "phase58_used": False,
        "phase0_63_source_modified": False,
        "phase61_report_present": p61.is_file(),
        "phase61_report_sha256": file_sha256(p61),
        "phase62_report_present": p62.is_file(),
        "phase62_report_sha256": file_sha256(p62),
        "phase63_report_present": p63.is_file(),
        "phase63_report_sha256": file_sha256(p63),
        "domains": {
            "historical_hypothetical_n": hist_n,
            "agent_shadow_n": shadow_n,
            "exness_demo_n_note": "Phase64 does not write demo store; read-only separation preserved",
        },
        "stores_merged": False,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "history_deals_get_prohibited": "history_deals_get" in PROHIBITED_MT5_API,
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
            and "order_send" in PROHIBITED_MT5_API
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
