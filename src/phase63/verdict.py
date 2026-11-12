"""Honest Phase 63 verdict selection."""

from __future__ import annotations

from typing import Any


def choose_verdict(
    *,
    metadata: dict[str, Any],
    import_result: dict[str, Any],
    sufficiency: dict[str, Any],
    integrity: dict[str, Any],
    tests_ok: bool,
    null_ok: bool,
) -> tuple[str, str]:
    if not null_ok or not tests_ok or not integrity.get("checks_pass"):
        return "EXNESS_DEMO_EVIDENCE_PARTIAL", "Safety/integrity/tests incomplete"

    if import_result.get("status") == "AWAITING_GENUINE_DEMO_EXPORT":
        return (
            "AWAITING_GENUINE_DEMO_EXPORT",
            "User-reported MT5 metadata registered; no genuine demo CSV export present to import",
        )

    if import_result.get("fabricated_evidence"):
        return "EXNESS_DEMO_EVIDENCE_PARTIAL", "Fabricated evidence detected — invalid"

    fills = int((sufficiency.get("observed") or {}).get("n_actual_fills") or 0)
    if fills > 0 and metadata.get("verification_status") and integrity.get("checks_pass"):
        if sufficiency.get("sufficient"):
            return (
                "EXNESS_DEMO_EVIDENCE_PIPELINE_READY",
                "Genuine imports present and sufficiency gates met (still not live authorization)",
            )
        return (
            "EXNESS_DEMO_EVIDENCE_PARTIAL",
            f"Pipeline functional with {fills} fills but evidence sufficiency gates not met",
        )

    return "EXNESS_DEMO_EVIDENCE_PARTIAL", "Metadata registered; import status incomplete"
