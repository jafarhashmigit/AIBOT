"""Research-use eligibility registry — never recycle consumed / sealed holdout."""

from __future__ import annotations

import json
from typing import Any

from phase58.data import chronological_splits
from phase65.consumption import build_consumption_registry
from phase66.constants import ELIGIBILITY_PATH, PHASE58_SPLITS, canonical_json_sha256


def build_eligibility_registry(*, new_live_days: list[str] | None = None) -> dict[str, Any]:
    p65 = build_consumption_registry()
    splits = chronological_splits()
    holdout = list(splits.get("holdout_sealed") or [])

    # Phase66 does not invent research dates. Newly collected live days → UNREVIEWED.
    by_day = dict(p65.get("status_by_day") or {})
    for d in holdout:
        by_day[d] = "SEALED"
    live_days = list(new_live_days or [])
    for d in live_days:
        if d not in by_day or by_day[d] not in (
            "SEALED",
            "CONSUMED_BY_DISCOVERY",
            "CONSUMED_BY_VALIDATION",
            "PHASE58_HOLDOUT_SEALED",
            "PHASE58_DISCOVERY_CONSUMED",
            "PHASE58_VALIDATION_CONSUMED",
        ):
            by_day[d] = "UNREVIEWED"

    out = {
        "phase58_holdout_sealed": holdout,
        "phase58_holdout_accessed": False,
        "phase65_history_preserved": True,
        "statuses": [
            "UNREVIEWED",
            "ELIGIBLE_FOR_DISCOVERY",
            "CONSUMED_BY_DISCOVERY",
            "CONSUMED_BY_VALIDATION",
            "RESERVED_FOR_CONFIRMATION",
            "SEALED",
            "EXCLUDED",
            "INVALID",
        ],
        "status_by_day": by_day,
        "new_live_collection_days": live_days,
        "independent_research_evidence_sufficient": False,
        "note": (
            "Ticks/snapshots ≠ independent sample size. Future research requires new "
            "preregistered protocol. Phase58 holdout outcomes not accessed."
        ),
        "evidence_generation_id": "phase66_collection_period_v1",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    ELIGIBILITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    ELIGIBILITY_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
