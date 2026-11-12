"""Research inventory — prior phases, retired families, cost status."""

from __future__ import annotations

import json
from typing import Any

from phase58.constants import DO_NOT_REPEAT as P58_DNR
from phase65.constants import (
    COST_MODEL_INCOMPLETE,
    DO_NOT_REPEAT,
    PROJECT_ROOT,
    UNAPPROVED,
    canonical_json_sha256,
)


def _read_json(rel: str) -> Any:
    p = PROJECT_ROOT / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def build_research_inventory() -> dict[str, Any]:
    p58_splits = _read_json("reports/phase58/dataset_splits.json") or {}
    p49 = _read_json("reports/phase49/final_verdict.json") or {}
    p59 = _read_json("reports/phase59/validation_results.json") or {}
    p6411 = _read_json("reports/phase64_11/verdict.json") or {}
    p6412 = _read_json("reports/phase64_12/verdict.json") or {}
    p6413 = _read_json("reports/phase64_13/verdict.json") or {}
    p58_md = (PROJECT_ROOT / "reports" / "phase58" / "FINAL_REPORT.md").is_file()
    p50_md = (PROJECT_ROOT / "reports" / "phase50" / "FINAL_REPORT.md").is_file()
    p51_md = (PROJECT_ROOT / "reports" / "phase51" / "FINAL_REPORT.md").is_file()

    tested = [
        {"id": "H58_P1_PRIOR_SESSION_LOCATION", "result": "FAILED", "phase": 58},
        {"id": "H58_W1_COSTLY_SPREAD_WAIT", "result": "FAILED", "phase": 58},
        {"id": "H58_I1_INACTIVITY_WAIT", "result": "FAILED", "phase": 58},
        {"id": "phase49_18_hypotheses", "result": "NO_INFORMATION_FAMILY_FOUND", "phase": 49},
        {"id": "phase50_adaptive_learning", "result": "NO_DEMONSTRATED_LEARNING_VALUE", "phase": 50},
        {"id": "phase51_shrink_bucket_v1", "result": "INDEPENDENT_CONFIRMATION_FAILED", "phase": 51},
    ]

    out = {
        "prior_phase_verdicts": {
            "phase49": p49.get("verdict") or "NO_INFORMATION_FAMILY_FOUND",
            "phase50": "NO_DEMONSTRATED_LEARNING_VALUE",
            "phase51": "INDEPENDENT_CONFIRMATION_FAILED",
            "phase58": "NO_INFORMATION_FAMILY_FOUND",
            "phase59_holdout_sealed": p59.get("holdout_sealed"),
            "phase64_11": p6411.get("verdict"),
            "phase64_12": p6412.get("verdict"),
            "phase64_13": p6413.get("verdict"),
        },
        "tested_hypotheses_summary": tested,
        "permanently_retired_families": list(DO_NOT_REPEAT),
        "phase58_do_not_repeat_n": len(P58_DNR),
        "phase58_splits_present": bool(p58_splits),
        "phase58_holdout_sealed": list(p58_splits.get("holdout_sealed") or []),
        "phase58_discovery": list(p58_splits.get("discovery") or []),
        "phase58_validation": list(p58_splits.get("validation") or []),
        "costs": {
            "spread": "VERIFIED_SNAPSHOT_OR_PATH_BIDASK",
            "slippage": "UNKNOWN",
            "commission": "UNKNOWN",
            "swap": "UNKNOWN_FOR_EXECUTION",
            "conversion": "UNKNOWN",
            "cost_model": COST_MODEL_INCOMPLETE,
            "risk_policy": UNAPPROVED,
        },
        "wait_baseline": "net_r=0 for abstention; mandatory comparator",
        "champion": "NO_MODEL",
        "production": "WAIT",
        "notes": [
            "Phase58 holdout must remain sealed unless a preregistered survivor exists",
            "Archive substrate is MetaQuotes-Demo XAUUSD; live broker is Exness XAUUSDm",
            "Exness session schedule applied as research filter with substrate limitation",
            f"phase58_report_present={p58_md}",
            f"phase50_report_present={p50_md}",
            f"phase51_report_present={p51_md}",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
