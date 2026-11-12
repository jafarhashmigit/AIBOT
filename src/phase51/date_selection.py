"""Performance-blind selection of new UNSEEN confirmation dates."""

from __future__ import annotations

import json
from typing import Any

from phase44.constants import DISCOVERY_DATES, VALIDATION_DATES
from phase51.constants import (
    N_DATES_TARGET,
    PHASE43_EXPOSURE,
    PHASE43_SELECTION,
    PHASE49_SELECTION,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase51.progress import write_json


def blocked_dates() -> set[str]:
    p43 = set(json.loads(PHASE43_SELECTION.read_text(encoding="utf-8"))["selected_dates"])
    p49 = json.loads(PHASE49_SELECTION.read_text(encoding="utf-8"))
    return (
        p43
        | set(p49["discovery_dates"])
        | set(p49["confirmation_dates"])
        | set(DISCOVERY_DATES)
        | set(VALIDATION_DATES)
    )


def remaining_pool() -> list[str]:
    exposure = json.loads(PHASE43_EXPOSURE.read_text(encoding="utf-8"))
    blocked = blocked_dates()
    pool = []
    for r in exposure.get("in_window_rows") or []:
        if r.get("exposure_class") != "UNSEEN":
            continue
        if not r.get("independent_validation_eligibility"):
            continue
        day = r["date"]
        if day in blocked:
            continue
        pool.append(day)
    return sorted(set(pool))


def select_evenly(pool: list[str], k: int) -> list[str]:
    pool = sorted(set(pool))
    if k >= len(pool):
        return pool
    if k <= 1:
        return pool[:1]
    selected: list[str] = []
    for i in range(k):
        idx = int(round(i * (len(pool) - 1) / (k - 1)))
        if pool[idx] not in selected:
            selected.append(pool[idx])
    for day in pool:
        if len(selected) >= k:
            break
        if day not in selected:
            selected.append(day)
    return sorted(selected)[:k]


def freeze_date_selection() -> dict[str, Any]:
    pool = remaining_pool()
    selected = select_evenly(pool, N_DATES_TARGET)
    report = {
        "algorithm": (
            "UNSEEN in-window eligible dates excluding Phase43 selected, Phase44 discovery+validation, "
            "Phase49 discovery+confirmation. Even spacing round(i*(n-1)/(k-1)). Performance-blind. "
            "Frozen before outcome evaluation."
        ),
        "pool_n": len(pool),
        "requested_k": N_DATES_TARGET,
        "selected_n": len(selected),
        "selected_dates": selected,
        "blocked_n": len(blocked_dates()),
        "selection_locked_before_evaluation": True,
        "one_shot": True,
    }
    report["selection_sha256"] = canonical_json_sha256(
        {k: v for k, v in report.items() if k != "selection_sha256"}
    )
    write_json(REPORTS_DIR / "date_selection.json", report)
    return report
