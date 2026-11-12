"""Phase53 final verdict selection."""

from __future__ import annotations

from typing import Any


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("data_integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(payload["data_integrity_failure"])

    if payload.get("insufficient_independent_data"):
        return "INSUFFICIENT_INDEPENDENT_DATA", str(payload["insufficient_independent_data"])

    disc = payload.get("discovery") or {}
    conf = payload.get("confirmation") or {}
    n_surv = int(disc.get("n_survivors") or 0)

    if n_surv == 0:
        return (
            "NO_EDGE_FOUND",
            "No preregistered family survived discovery gates vs WAIT/BUY/SELL/random/static/stress/LODO.",
        )

    if not conf.get("opened"):
        return (
            "NO_EDGE_FOUND",
            f"{n_surv} discovery survivor(s) but confirmation was not opened.",
        )

    if int(conf.get("n_confirmed") or 0) > 0:
        return (
            "INDEPENDENT_EDGE_CONFIRMED",
            f"Confirmed families: {conf.get('confirmed_ids')}",
        )

    return (
        "INDEPENDENT_CONFIRMATION_FAILED",
        f"Discovery survivors {disc.get('survivors')} failed sealed confirmation.",
    )
