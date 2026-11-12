"""Phase 64.9 multi-dimension verdict."""

from __future__ import annotations

from typing import Any

from phase64_9.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    LIVE_TRADING,
    ORDER_SEND,
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    UNAPPROVED,
)


def choose_verdict(
    *,
    security_review: dict[str, Any],
    path_trace: dict[str, Any],
    preflight_ok: bool,
    intent_ok: bool,
    fake_ok: bool,
    recovery_ok: bool,
    auth_ok: bool,
    adversarial_ok: bool,
    integrity_ok: bool,
    risk_calc_ok: bool,
    tests_ok: bool,
    regressions_ok: bool,
) -> dict[str, Any]:
    dims = {
        "order_submission_security": "PASS" if security_review.get("pass") and path_trace.get("pass") else "BLOCKED",
        "preflight_validation": "PASS" if preflight_ok else "BLOCKED",
        "execution_intent_durability": "PASS" if intent_ok else "BLOCKED",
        "fake_broker_execution": "PASS" if fake_ok else "BLOCKED",
        "timeout_recovery_safety": "PASS" if recovery_ok else "BLOCKED",
        "broker_reconciliation": "DESIGN_VALIDATED_VIA_SYNTHETIC_RO_PATH" if recovery_ok else "BLOCKED",
        "authorization_security": "PASS" if auth_ok else "BLOCKED",
        "cost_completeness": "INCOMPLETE",
        "risk_policy_approval": UNAPPROVED,
        "actual_broker_deals": "NONE_TRADE_FILLS",
    }

    core = all(
        [
            security_review.get("pass"),
            path_trace.get("pass"),
            preflight_ok,
            intent_ok,
            fake_ok,
            recovery_ok,
            auth_ok,
            adversarial_ok,
            integrity_ok,
            risk_calc_ok,
            tests_ok,
            regressions_ok,
            BROKER_SUBMISSION_ENABLED is False,
            BROKER_EXECUTION_AUTHORIZED is False,
        ]
    )

    if core:
        verdict = "EXECUTION_PREFLIGHT_VALIDATED"
        reason = (
            "Preflight/intent/auth/fake-broker/recovery validated; order_send remains PROHIBITED; "
            "submission hard-disabled; not broker execution authorization"
        )
    elif security_review.get("pass") and (preflight_ok or fake_ok):
        verdict = "EXECUTION_PREFLIGHT_PARTIAL"
        reason = "Partial preflight architecture; see failed dimensions"
    else:
        verdict = "EXECUTION_PREFLIGHT_BLOCKED"
        reason = "Critical preflight/security blockers remain"

    return {
        "verdict": verdict,
        "reason": reason,
        "dimensions": dims,
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
            "Phase65": PHASE65,
        },
        "not_broker_execution_authorization": True,
    }
