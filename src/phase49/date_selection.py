"""Deterministic selection of 40 remaining UNSEEN dates — freeze BEFORE acquisition."""

from __future__ import annotations

import json
from typing import Any

from phase49.constants import (
    FORBIDDEN_VALIDATION_DATES,
    MAX_DATES,
    N_CONFIRMATION,
    N_DISCOVERY,
    PHASE43_EXPOSURE,
    PHASE43_SELECTION,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase49.progress import write_json


def remaining_unseen_pool() -> dict[str, Any]:
    exposure = json.loads(PHASE43_EXPOSURE.read_text(encoding="utf-8"))
    prior_sel = json.loads(PHASE43_SELECTION.read_text(encoding="utf-8"))
    previously_selected = set(prior_sel.get("selected_dates") or [])

    pool = []
    excluded = {"previously_selected": [], "partial": [], "previous": [], "unknown": [], "forbidden_val": []}
    for r in exposure.get("in_window_rows") or []:
        day = r["date"]
        cls = r["exposure_class"]
        if cls == "PARTIALLY_EXPOSED":
            excluded["partial"].append(day)
            continue
        if cls == "PREVIOUSLY_EXPOSED":
            excluded["previous"].append(day)
            continue
        if cls == "UNKNOWN":
            excluded["unknown"].append(day)
            continue
        if cls != "UNSEEN":
            continue
        if day in previously_selected:
            excluded["previously_selected"].append(day)
            continue
        if day in FORBIDDEN_VALIDATION_DATES:
            excluded["forbidden_val"].append(day)
            continue
        if not r.get("independent_validation_eligibility"):
            continue
        pool.append(day)

    pool = sorted(set(pool))
    return {
        "pool": pool,
        "pool_n": len(pool),
        "excluded_counts": {k: len(set(v)) for k, v in excluded.items()},
        "previously_selected_n": len(previously_selected),
    }


def select_evenly(pool: list[str], k: int = MAX_DATES) -> list[str]:
    pool = sorted(set(pool))
    if k >= len(pool):
        return pool
    if k <= 1:
        return pool[:1]
    selected: list[str] = []
    for i in range(k):
        idx = int(round(i * (len(pool) - 1) / (k - 1)))
        day = pool[idx]
        if day not in selected:
            selected.append(day)
    for day in pool:
        if len(selected) >= k:
            break
        if day not in selected:
            selected.append(day)
    return sorted(selected)[:k]


def freeze_date_selection() -> dict[str, Any]:
    """Record selection procedure and freeze date list + SHA before accessing outcomes."""
    meta = remaining_unseen_pool()
    selected = select_evenly(meta["pool"], MAX_DATES)
    # Chronological split: first 25 discovery, last 15 confirmation
    selected_sorted = sorted(selected)
    discovery = selected_sorted[:N_DISCOVERY]
    confirmation = selected_sorted[N_DISCOVERY : N_DISCOVERY + N_CONFIRMATION]

    report: dict[str, Any] = {
        "algorithm": (
            "From Phase43 in-window UNSEEN weekdays with independent_validation_eligibility, "
            "exclude Phase43 selected_dates, PARTIALLY_EXPOSED, PREVIOUSLY_EXPOSED, UNKNOWN, "
            "and Phase44 validation dates. Evenly space k=40 via round(i*(n-1)/(k-1)). "
            "Sort chronologically; first 25=discovery, last 15=confirmation. "
            "No outcome/performance-based selection."
        ),
        "pool_n": meta["pool_n"],
        "excluded_counts": meta["excluded_counts"],
        "requested_k": MAX_DATES,
        "selected_n": len(selected_sorted),
        "selected_dates": selected_sorted,
        "discovery_dates": discovery,
        "confirmation_dates": confirmation,
        "confirmation_sealed": True,
        "selection_locked_before_acquisition": True,
        "forbidden_validation_excluded": True,
        "months_represented": sorted({d[:7] for d in selected_sorted}),
    }
    report["selection_sha256"] = canonical_json_sha256(
        {k: v for k, v in report.items() if k != "selection_sha256"}
    )
    write_json(REPORTS_DIR / "date_selection.json", report)
    return report
