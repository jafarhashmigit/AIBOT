"""Honest Phase 64.2 verdict."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    crash_ok: bool,
    adversarial_ok: bool,
    integrity_ok: bool,
    tests_ok: bool,
    null_ok: bool,
    consistency_ok: bool,
) -> tuple[str, str]:
    if not (null_ok and tests_ok and integrity_ok):
        return "INTENT_IDENTITY_WAIT_DURABILITY_PARTIAL", "Safety/integrity/tests incomplete"
    if not crash_ok or not adversarial_ok or not consistency_ok:
        return "INTENT_IDENTITY_WAIT_DURABILITY_PARTIAL", "Hardening suites incomplete"
    return (
        "INTENT_IDENTITY_WAIT_DURABILITY_HARDENED",
        "Intent terminal states, bar identity stability, and durable WAIT recovery verified "
        "(still NO_MODEL / WAIT / no broker orders)",
    )
