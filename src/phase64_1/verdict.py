"""Honest Phase 64.1 verdict."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    integration_ok: bool,
    crash_ok: bool,
    adversarial_ok: bool,
    integrity_ok: bool,
    tests_ok: bool,
    null_ok: bool,
    end_to_end_paper: bool,
) -> tuple[str, str]:
    if not (null_ok and tests_ok and integrity_ok):
        return (
            "CANONICAL_DECISION_INTENT_INTEGRATION_PARTIAL",
            "Safety/integrity/tests incomplete",
        )
    if not crash_ok or not adversarial_ok:
        return (
            "CANONICAL_DECISION_INTENT_INTEGRATION_PARTIAL",
            "Crash or adversarial suite incomplete",
        )
    if not integration_ok or not end_to_end_paper:
        return (
            "CANONICAL_DECISION_INTENT_INTEGRATION_PARTIAL",
            "Integration remains scaffold-only or end-to-end paper path incomplete",
        )
    return (
        "CANONICAL_DECISION_INTENT_INTEGRATION_READY",
        "Paper lifecycle uses canonical identity, immutable snapshot, and durable intent end-to-end "
        "(still NO_MODEL / WAIT / no broker orders)",
    )
