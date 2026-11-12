"""Honest Phase 64.3 verdict."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    adoption_ok: bool,
    multibar_ok: bool,
    recovery_ok: bool,
    xau_ok: bool,
    integrity_ok: bool,
    tests_ok: bool,
    null_ok: bool,
) -> tuple[str, str]:
    if not (null_ok and tests_ok and integrity_ok):
        return "HARDENED_RUNTIME_ADOPTION_FAILED", "Safety/integrity/tests incomplete"
    if not (adoption_ok and xau_ok):
        return "HARDENED_RUNTIME_ADOPTION_PARTIAL", "Approved-path adoption or XAUUSDm integrity incomplete"
    if not multibar_ok or not recovery_ok:
        return "HARDENED_RUNTIME_ADOPTION_PARTIAL", "Multi-bar or recovery validation incomplete"
    return (
        "HARDENED_RUNTIME_ADOPTION_VALIDATED",
        "Approved paper runtime uses hardened engine; multi-bar and recovery validated "
        "(still NO_MODEL / WAIT / no broker orders)",
    )
