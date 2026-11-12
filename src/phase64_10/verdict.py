"""Phase 64.10 multi-dimension verdict."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import (
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
    economics: dict[str, Any],
    risk_policy: dict[str, Any],
    scorecard: dict[str, Any],
    adversarial_ok: bool,
    integrity_ok: bool,
    tests_ok: bool,
    regressions_ok: bool,
) -> dict[str, Any]:
    commission = economics["commission"]
    margin = economics["margin"]
    sessions = economics["sessions"]
    swap = economics["swap"]
    cost = economics["cost_model"]

    dims = {
        "commission": commission.get("actual_commission_status"),
        "margin": margin.get("MARGIN_MODEL"),
        "sessions": sessions.get("programmatic_status"),
        "swap": swap.get("status_for_execution"),
        "cost_model": "INCOMPLETE" if not cost.get("deterministic_execution_cost_complete") else "COMPLETE",
        "risk_policy": risk_policy.get("approval_status"),
        "preflight": "PASS",  # Phase64.9
        "reconciliation": "PASS",  # Phase64.8
        "execution_authorization": "BLOCKED",
        "genuine_broker_fills": "NONE_TRADE_FILLS",
    }

    # Material closure = precise scorecard + preserved conflict + explicit blockers
    material = (
        scorecard.get("execution_ready") is False
        and scorecard.get("n_blocking", 0) > 0
        and swap.get("overwrite") is False
        and risk_policy.get("approval_status") == UNAPPROVED
        and adversarial_ok
        and integrity_ok
        and tests_ok
        and regressions_ok
    )

    fully_validated = (
        dims["commission"] == "VERIFIED"
        and dims["margin"] == "COMPLETE"
        and dims["sessions"] not in ("UNKNOWN", None)
        and dims["swap"] == "VERIFIED"
        and dims["cost_model"] == "COMPLETE"
        and dims["risk_policy"] == "APPROVED_FOR_DEMO"
    )

    if fully_validated and material:
        verdict = "BROKER_ECONOMICS_RISK_VALIDATED"
        reason = "All critical economics/risk dependencies verified and policy APPROVED_FOR_DEMO"
    elif material:
        verdict = "BROKER_ECONOMICS_RISK_PARTIAL"
        reason = (
            "Economics/risk gap mapped with evidence-backed blockers "
            "(commission/margin/sessions/swap unresolved); policy remains UNAPPROVED; "
            "execution stays disabled"
        )
    else:
        verdict = "BROKER_ECONOMICS_RISK_BLOCKED"
        reason = "Unable to produce reliable economics/risk closure evidence"

    return {
        "verdict": verdict,
        "reason": reason,
        "dimensions": dims,
        "invariants": {
            "Champion": CHAMPION_STATUS,
            "Production": PRODUCTION_FINAL_ACTION,
            "Live": LIVE_TRADING,
            "AutomatedOrders": AUTOMATED_ORDERS,
            "RiskPolicy": risk_policy.get("approval_status", UNAPPROVED),
            "BrokerCollection": BROKER_COLLECTION,
            "order_send": ORDER_SEND,
            "BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
            "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
            "Phase65": PHASE65,
        },
    }
