"""Phase 64.12 verdict — session evidence quality only."""

from __future__ import annotations

from typing import Any

from phase64_12.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COST_MODEL_INCOMPLETE,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    UNAPPROVED,
    VERDICT_BLOCKED,
    VERDICT_PARTIAL,
    VERDICT_VALIDATED,
)


def choose_verdict(
    *,
    applicability_justified: bool,
    authoritative_hours: bool,
    timezone_established: bool,
    dst_handled: bool,
    provenance_ok: bool,
    tests_ok: bool,
    adversarial_ok: bool,
    integrity_ok: bool,
    regressions_ok: bool,
    third_party_used: bool,
) -> dict[str, Any]:
    base_ok = (
        authoritative_hours
        and applicability_justified
        and timezone_established
        and dst_handled
        and provenance_ok
        and tests_ok
        and adversarial_ok
        and integrity_ok
        and regressions_ok
        and not third_party_used
    )

    if base_ok:
        verdict = VERDICT_VALIDATED
        reason = (
            "Authoritative Exness Help Center hours for XAUUSD applied to XAUUSDm via official "
            "Standard -m suffix mapping; UTC timezone + US-DST season windows verified; "
            "provenance journaled; tests/regressions pass. OPEN does not authorize execution."
        )
    elif authoritative_hours and not applicability_justified:
        verdict = VERDICT_PARTIAL
        reason = "Hours found for XAUUSD but exact-symbol applicability not justified"
    elif authoritative_hours or applicability_justified:
        verdict = VERDICT_PARTIAL
        reason = "Partial session evidence; see failed gates"
    else:
        verdict = VERDICT_BLOCKED
        reason = "Unable to establish authoritative XAUUSDm session evidence"

    return {
        "verdict": verdict,
        "reason": reason,
        "gates": {
            "authoritative_hours": authoritative_hours,
            "applicability_justified": applicability_justified,
            "timezone_established": timezone_established,
            "dst_handled": dst_handled,
            "provenance_ok": provenance_ok,
            "tests_ok": tests_ok,
            "adversarial_ok": adversarial_ok,
            "integrity_ok": integrity_ok,
            "regressions_ok": regressions_ok,
            "third_party_used": third_party_used,
        },
        "invariants": {
            "Champion": CHAMPION_STATUS,
            "Production": PRODUCTION_FINAL_ACTION,
            "Live": LIVE_TRADING,
            "AutomatedOrders": AUTOMATED_ORDERS,
            "RiskPolicy": UNAPPROVED,
            "CostModel": COST_MODEL_INCOMPLETE,
            "BrokerCollection": BROKER_COLLECTION,
            "order_send": ORDER_SEND,
            "BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
            "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
            "GenuineFills": GENUINE_FILLS,
            "Phase65": PHASE65,
        },
        "does_not_authorize_execution": True,
    }
