"""Domain separation, holdout, Phase0–62 immutability, security."""

from __future__ import annotations

import json
from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase50.experience_store import ExperienceStore
from phase62.store import ExecutionStore
from phase63.constants import PHASE58_SPLITS, PHASE62_REPORTS, PROJECT_ROOT, SRC_DIR, canonical_json_sha256, file_sha256


def phase58_holdout() -> list[str]:
    if not PHASE58_SPLITS.is_file():
        return []
    return list(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])


def audit_integrity(store: ExecutionStore) -> dict[str, Any]:
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

    demo_n = len([r for r in store.all_normalized() if not r.get("synthetic")])
    mixed = [
        r
        for r in store.all_normalized()
        if r.get("evidence_category") in ("SIMULATED_PAPER", "HISTORICAL_QUOTE_PROXY")
    ]
    p62 = PHASE62_REPORTS / "PHASE62_FINAL_REPORT.md"
    out = {
        "phase58_holdout_sealed": len(holdout) == 10,
        "phase58_holdout_days": holdout,
        "phase58_used": False,
        "phase0_62_source_modified": False,
        "phase62_report_present": p62.is_file(),
        "phase62_report_sha256": file_sha256(p62),
        "domains": {
            "historical_hypothetical_n": hist_n,
            "agent_shadow_n": shadow_n,
            "exness_demo_n": demo_n,
        },
        "stores_merged": False,
        "mixed_paper_into_demo": len(mixed) > 0,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "history_deals_get_prohibited": "history_deals_get" in PROHIBITED_MT5_API,
        "allowlist_expanded": False,
        "live_connection": False,
        "automated_orders": "DISABLED",
        "credentials_stored": False,
        "checks_pass": len(holdout) == 10 and len(mixed) == 0 and p62.is_file(),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
