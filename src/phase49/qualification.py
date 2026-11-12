"""Phase49 verdict selection."""

from __future__ import annotations

from typing import Any


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("data_integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(payload.get("data_integrity_failure"))
    if payload.get("research_design_failure"):
        return "RESEARCH_DESIGN_FAILURE", str(payload.get("research_design_failure"))

    acq = payload.get("acquisition") or {}
    n_complete = len(acq.get("completed_dates") or [])
    if n_complete < 10:
        return (
            "INSUFFICIENT_DATA",
            f"Only {n_complete} complete dates acquired (need usable discovery coverage).",
        )

    disc = payload.get("discovery") or {}
    n_surv = int(disc.get("n_survivors") or 0)
    conf = payload.get("confirmation") or {}

    if n_surv == 0:
        return (
            "NO_INFORMATION_FAMILY_FOUND",
            "No pre-registered hypothesis survived Bonferroni/date-block/LODO/cost-stress on discovery.",
        )

    if not conf.get("opened"):
        return (
            "PROMISING_DISCOVERY_UNCONFIRMED",
            f"{n_surv} discovery survivor(s) but confirmation not opened/completed.",
        )

    if conf.get("n_confirmed", 0) > 0:
        return (
            "INDEPENDENT_EDGE_CONFIRMED",
            f"Confirmed on sealed dates: {conf.get('confirmed_ids')}",
        )

    return (
        "PROMISING_DISCOVERY_UNCONFIRMED",
        f"Discovery survivors {disc.get('survivors')} failed independent confirmation.",
    )
