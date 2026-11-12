"""Future research eligibility — no outcome-based allocation."""

from __future__ import annotations

from typing import Any

from phase43.progress import write_json


def build_eligibility(
    *,
    exposure: dict[str, Any],
    selection: dict[str, Any],
    quality: dict[str, Any],
    acquisition: dict[str, Any],
) -> dict[str, Any]:
    completed = set(acquisition.get("completed_dates") or [])
    quality_by = {r["day"]: r for r in (quality.get("rows") or [])}

    unseen_ready = []
    for day in selection.get("selected_dates") or []:
        q = quality_by.get(day) or {}
        if day not in completed:
            continue
        if q.get("session_status") != "VERIFIED_COMPLETE_SESSION":
            continue
        if not q.get("h1_warmup_sufficient_30"):
            continue
        if not q.get("ema20_ready"):
            continue
        if (q.get("m5_n") or 0) <= 0:
            continue
        unseen_ready.append(day)

    partial = [
        r["date"]
        for r in (exposure.get("in_window_rows") or [])
        if r["exposure_class"] == "PARTIALLY_EXPOSED"
    ]
    previous = [
        r["date"]
        for r in (exposure.get("in_window_rows") or [])
        if r["exposure_class"] == "PREVIOUSLY_EXPOSED"
    ]

    # Proposed chronological split among ready unseen dates — no outcome peeking
    ready = sorted(unseen_ready)
    mid = len(ready) // 2
    allocation = {
        "discovery_candidate_dates": ready[:mid],
        "validation_candidate_dates": ready[mid:],
        "note": (
            "Proposed chronological split only. Do not reallocate based on returns. "
            "These dates remain unused for hypothesis scoring in Phase43."
        ),
    }

    payload = {
        "A_truly_unseen_independent_validation_eligible": ready,
        "A_n": len(ready),
        "B_partially_exposed_exploratory_only": sorted(partial),
        "B_n": len(partial),
        "C_previously_exposed_prohibited_as_independent": sorted(previous),
        "C_n": len(previous),
        "proposed_chronological_allocation": allocation,
        "acquired_but_not_complete": [
            d for d in (acquisition.get("completed_dates") or []) if d not in ready
        ]
        + list(acquisition.get("pending_dates") or []),
    }
    write_json("future_research_eligibility.json", payload)
    return payload
