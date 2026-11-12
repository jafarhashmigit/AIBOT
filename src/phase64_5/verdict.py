"""Phase64.5 verdict selection."""

from __future__ import annotations

from typing import Any


def choose_verdict(bundle: dict[str, Any]) -> tuple[str, str]:
    arch = bundle.get("architecture") or {}
    formats = bundle.get("formats") or {}
    discovery = bundle.get("discovery") or {}
    genuine = bundle.get("genuine_import") or {}
    adversarial = bundle.get("adversarial") or {}
    recovery = bundle.get("recovery") or {}
    integrity = bundle.get("integrity") or {}
    tests = bundle.get("unit_tests") or {}
    recon = bundle.get("reconciliation") or {}

    safety_ok = (
        integrity.get("checks_pass")
        and adversarial.get("suite_pass")
        and recovery.get("suite_pass")
        and tests.get("ok")
        and arch.get("pass")
        and formats.get("pass")
    )
    # Honest zero genuine trades is OK for VALIDATED if foundation works
    counts = (genuine.get("counts") or {})
    genuine_deals = int(counts.get("genuine_broker_deals") or 0)
    fabricated = genuine.get("fabricated_evidence") is False
    read_only = genuine.get("read_only") is not False

    if safety_ok and fabricated and read_only and recon.get("silently_reconciled_unknowns") is False:
        if genuine_deals == 0:
            return (
                "BROKER_EVIDENCE_RECONCILIATION_VALIDATED",
                "Foundation validated with SIMULATED_FIXTURE tests; genuine XAUUSDm trade deals = 0 (honest)",
            )
        return (
            "BROKER_EVIDENCE_RECONCILIATION_VALIDATED",
            "Genuine broker evidence ingested and reconciled without fabricated links",
        )
    if any([safety_ok, arch.get("pass"), formats.get("pass")]):
        return (
            "BROKER_EVIDENCE_RECONCILIATION_PARTIAL",
            "Some ingestion/recon/safety checks incomplete or failed",
        )
    return "BROKER_EVIDENCE_RECONCILIATION_FAILED", "Critical evidence foundation checks failed"
