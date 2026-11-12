"""Honest Phase 64 readiness verdict — never claims broker execution readiness without genuine evidence."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    lifecycle: dict[str, Any],
    crash_suite: dict[str, Any],
    traceability: dict[str, Any],
    integrity: dict[str, Any],
    tests_ok: bool,
    null_ok: bool,
    genuine_broker_fills: int = 0,
) -> tuple[str, str]:
    if not null_ok or not tests_ok or not integrity.get("checks_pass"):
        return (
            "DEMO_DECISION_EXECUTION_READINESS_PARTIAL",
            "Safety/integrity/tests incomplete",
        )

    if not crash_suite.get("suite_pass"):
        return (
            "DEMO_DECISION_EXECUTION_READINESS_PARTIAL",
            "Crash/recovery suite failures remain",
        )

    missing = (lifecycle.get("summary") or {}).get("missing") or []
    if "FUTURE_BROKER_ORDER" in missing and genuine_broker_fills == 0:
        return (
            "DEMO_DECISION_EXECUTION_READINESS_PARTIAL",
            "Architecture scaffold + crash tests pass; FUTURE_BROKER_ORDER unauthorized; "
            "no genuine linked demo fills — not broker-execution-ready",
        )

    if genuine_broker_fills > 0 and not (traceability.get("genuine_broker_orders_linked") or 0):
        return (
            "DEMO_DECISION_EXECUTION_READINESS_PARTIAL",
            "Genuine fills exist elsewhere but decision↔broker linkage not production-wired",
        )

    # Even if somehow wired, Phase64 never authorizes live/automated trading
    return (
        "DEMO_DECISION_EXECUTION_READINESS_PARTIAL",
        "Readiness audit complete with remaining authorization and evidence gaps",
    )
