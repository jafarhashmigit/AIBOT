"""Deterministic independent date selection — frozen before evaluation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from phase36.constants import (
    EXCLUDED_EVAL_DAYS,
    MAX_SELECTED_DATES,
    WINDOW_END,
    WINDOW_START,
)
from phase36.progress import write_json


def candidate_weekdays() -> list[str]:
    out: list[date] = []
    d = WINDOW_START
    while d <= WINDOW_END:
        if d.weekday() < 5:
            iso = d.isoformat()
            if iso not in EXCLUDED_EVAL_DAYS:
                out.append(d)
        d += timedelta(days=1)
    return [x.isoformat() for x in out]


def select_independent_dates(k: int = MAX_SELECTED_DATES) -> dict[str, Any]:
    pool = candidate_weekdays()
    if k >= len(pool):
        selected = pool
    elif k <= 1:
        selected = pool[:1]
    else:
        selected = []
        for i in range(k):
            idx = int(round(i * (len(pool) - 1) / (k - 1)))
            day = pool[idx]
            if day not in selected:
                selected.append(day)
        # If rounding collisions shortened list, fill forward from pool
        for day in pool:
            if len(selected) >= k:
                break
            if day not in selected:
                selected.append(day)
        selected = sorted(selected)[:k]

    assert not (set(selected) & EXCLUDED_EVAL_DAYS), "excluded days leaked into selection"
    report = {
        "algorithm": (
            "Evenly spaced Mon–Fri in window excluding Phase34/35 evaluated days; "
            "deterministic index round(i*(n-1)/(k-1)); no performance-based selection."
        ),
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "excluded_eval_days": sorted(EXCLUDED_EVAL_DAYS),
        "candidate_pool_n": len(pool),
        "selected_n": len(selected),
        "selected_dates": selected,
        "selection_locked_before_evaluation": True,
    }
    write_json("date_selection.json", report)
    return report
