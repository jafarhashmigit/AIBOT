"""Performance-blind selection of eligible discovery + sealed confirmation dates."""

from __future__ import annotations

from typing import Any

from phase53.constants import (
    N_CONFIRMATION,
    N_DATES_TARGET,
    N_DISCOVERY,
    REPORTS_DIR,
    canonical_json_sha256,
)
from phase53.exposure_audit import build_exposure_ledger
from phase53.progress import write_json


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


def freeze_date_selection(ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    ledger = ledger or build_exposure_ledger()
    pool = list(ledger.get("eligible_unseen_dates") or [])
    selected = select_evenly(pool, N_DATES_TARGET)
    selected_sorted = sorted(selected)
    discovery = selected_sorted[:N_DISCOVERY]
    confirmation = selected_sorted[N_DISCOVERY : N_DISCOVERY + N_CONFIRMATION]

    report: dict[str, Any] = {
        "algorithm": (
            "From GENUINELY_UNSEEN_ELIGIBLE weekdays after excluding Phase43/44 discovery, "
            "Phase44 validation, Phase49 discovery+confirmation, Phase51 confirmation, and "
            "partial/unknown/previously-exposed classes. Even spacing round(i*(n-1)/(k-1)). "
            "Chronological split: first 20 discovery, last 10 confirmation (sealed until freeze)."
        ),
        "pool_n": len(pool),
        "requested_k": N_DATES_TARGET,
        "selected_n": len(selected_sorted),
        "selected_dates": selected_sorted,
        "discovery_dates": discovery,
        "confirmation_dates": confirmation,
        "confirmation_sealed": True,
        "selection_locked_before_acquisition": True,
        "performance_blind": True,
        "months_represented": sorted({d[:7] for d in selected_sorted}),
        "never_open_respected": True,
    }
    report["selection_sha256"] = canonical_json_sha256(
        {k: v for k, v in report.items() if k != "selection_sha256"}
    )
    write_json(REPORTS_DIR / "date_selection.json", report)
    return report
