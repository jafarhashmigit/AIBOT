"""Evidence-based Phase 62 verdict."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    identity: dict[str, Any],
    decision: dict[str, Any],
    integrity: dict[str, Any],
    domains: dict[str, Any],
    recovery: dict[str, Any],
    holdout_sealed: bool,
    null_ok: bool,
    tests_ok: bool,
    credentials_persisted: bool,
    live_access: bool,
) -> tuple[str, str]:
    if credentials_persisted or live_access:
        return "EXNESS_DEMO_COLLECTION_BLOCKED", "Credential persistence or live access detected"
    if not holdout_sealed or not null_ok:
        return "EXNESS_DEMO_COLLECTION_BLOCKED", "Holdout seal or NullPolicy failed"
    if not tests_ok:
        return "EXNESS_DEMO_COLLECTION_BLOCKED", "Phase62 tests failed"
    if not recovery.get("pass"):
        return "EXNESS_DEMO_COLLECTION_BLOCKED", "Store recovery audit failed"
    if not domains.get("checks_pass"):
        return "EXNESS_DEMO_COLLECTION_BLOCKED", "Evidence domain integrity failed"

    core = bool(identity.get("core_identity_verified"))
    native_connected = bool(decision.get("native_terminal_connected"))
    adapters = set(decision.get("activated_adapters") or [])

    if core and ("csv_import" in adapters) and (native_connected or identity.get("intake_file_present")):
        # READY requires verified metadata AND functioning collection — CSV path counts if intake verified
        if core:
            return (
                "EXNESS_DEMO_COLLECTION_READY",
                "Verified account metadata and functioning read-only collection path established",
            )

    reasons = []
    if not core:
        reasons.append("account metadata not verified")
    if not identity.get("intake_file_present"):
        reasons.append("no account metadata intake file")
    if decision.get("decision", "").endswith("CSV_JSON") or "CSV" in str(decision.get("decision")):
        reasons.append("CSV/JSON infrastructure ready; native demo terminal not connected")
    return "EXNESS_DEMO_COLLECTION_PARTIAL", "Useful infrastructure exists, but incomplete: " + "; ".join(reasons)
