"""Phase 64.11 verdict — boundary quality, not economics completeness."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    UNAPPROVED,
)


def choose_verdict(
    *,
    matrix: dict[str, Any],
    adversarial_ok: bool,
    integrity_ok: bool,
    tests_ok: bool,
    regressions_ok: bool,
) -> dict[str, Any]:
    arts = matrix.get("artifacts") or {}
    dims = {
        "commission": arts.get("commission", {}).get("classification"),
        "margin": arts.get("margin", {}).get("classification"),
        "sessions": arts.get("sessions", {}).get("classification"),
        "swap": arts.get("swap", {}).get("classification"),
        "cost_model": arts.get("cost", {}).get("COST_MODEL_VALIDATED"),
        "risk_policy": arts.get("risk_policy", {}).get("overall_approval_status"),
        "matrix_consistent": matrix.get("matrix_consistent"),
        "forced_closure": matrix.get("forced_closure"),
        "execution_authorization": "BLOCKED",
        "genuine_fills": GENUINE_FILLS,
    }

    # VALIDATED = rigorous boundary for every blocker, concrete next evidence, no forced closure
    rows = matrix.get("rows") or []
    every_has_next = all(r.get("next_evidence") for r in rows)
    every_has_class = all(r.get("classification") for r in rows)
    boundary_ok = (
        matrix.get("matrix_consistent")
        and matrix.get("forced_closure") is False
        and every_has_next
        and every_has_class
        and adversarial_ok
        and integrity_ok
        and tests_ok
        and regressions_ok
    )

    # Economics still incomplete — that is expected and does not prevent VALIDATED boundary
    economics_complete = bool(arts.get("cost", {}).get("COST_MODEL_VALIDATED")) and arts.get(
        "risk_policy", {}
    ).get("overall_approval_status") == "APPROVED_FOR_DEMO"

    if boundary_ok and not economics_complete:
        verdict = "BROKER_EVIDENCE_BOUNDARY_VALIDATED"
        reason = (
            "Evidence boundary rigorously established for every remaining blocker with justified "
            "classifications and concrete next-evidence requirements; economics remain incomplete "
            "by design (not forced closed)"
        )
    elif boundary_ok and economics_complete:
        verdict = "BROKER_EVIDENCE_BOUNDARY_VALIDATED"
        reason = "Boundary validated and economics unexpectedly complete"
    elif matrix.get("matrix_consistent") and (adversarial_ok or tests_ok):
        verdict = "BROKER_EVIDENCE_BOUNDARY_PARTIAL"
        reason = "Partial evidence-boundary documentation; see failed checks"
    else:
        verdict = "BROKER_EVIDENCE_BOUNDARY_BLOCKED"
        reason = "Unable to establish a consistent evidence boundary"

    return {
        "verdict": verdict,
        "reason": reason,
        "dimensions": dims,
        "not_claiming_economics_fully_known": True,
        "invariants": {
            "Champion": CHAMPION_STATUS,
            "Production": PRODUCTION_FINAL_ACTION,
            "Live": LIVE_TRADING,
            "AutomatedOrders": AUTOMATED_ORDERS,
            "RiskPolicy": UNAPPROVED,
            "BrokerCollection": BROKER_COLLECTION,
            "order_send": ORDER_SEND,
            "BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
            "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
            "GenuineFills": GENUINE_FILLS,
            "Phase65": PHASE65,
        },
    }
