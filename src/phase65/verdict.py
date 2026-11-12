"""Phase 65 research verdict — never force Champion promotion."""

from __future__ import annotations

from typing import Any

from phase65.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COST_MODEL_INCOMPLETE,
    EXECUTION_AUTHORIZATION,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    UNAPPROVED,
    VERDICT_BLOCKED,
    VERDICT_INCONCLUSIVE,
    VERDICT_NONE,
    VERDICT_PENDING,
    VERDICT_VALIDATED,
)


def choose_verdict(
    *,
    sufficient_data: bool,
    leakage_ok: bool,
    integrity_ok: bool,
    tests_ok: bool,
    survivors_discovery: list[str],
    survivors_validation: list[str],
    holdout_opened: bool,
    holdout_confirmed: bool,
    budget_exhausted: bool,
) -> dict[str, Any]:
    if not sufficient_data:
        verdict = VERDICT_BLOCKED
        reason = "Insufficient unconsumed eligible data for independent discovery design"
    elif not leakage_ok or not integrity_ok or not tests_ok:
        verdict = VERDICT_BLOCKED
        reason = "Leakage/integrity/tests failed"
    elif survivors_validation and holdout_confirmed:
        verdict = VERDICT_VALIDATED
        reason = "Independent validation + single holdout confirmation passed (research-only)"
    elif survivors_validation and not holdout_opened:
        verdict = VERDICT_PENDING
        reason = "Validation survivors exist; holdout not opened in this phase (pending confirmation)"
    elif survivors_discovery and not survivors_validation:
        verdict = VERDICT_INCONCLUSIVE
        reason = "Discovery signal did not survive validation"
    elif budget_exhausted and not survivors_discovery:
        verdict = VERDICT_NONE
        reason = "Hypothesis budget exhausted; no family survived discovery gates vs WAIT"
    else:
        verdict = VERDICT_INCONCLUSIVE
        reason = "No conclusive independent edge"

    return {
        "verdict": verdict,
        "reason": reason,
        "survivors_discovery": survivors_discovery,
        "survivors_validation": survivors_validation,
        "holdout_opened": holdout_opened,
        "holdout_confirmed": holdout_confirmed,
        "champion_remains": CHAMPION_STATUS,
        "production_remains": PRODUCTION_FINAL_ACTION,
        "invariants": {
            "Champion": CHAMPION_STATUS,
            "Production": PRODUCTION_FINAL_ACTION,
            "Live": LIVE_TRADING,
            "AutomatedOrders": AUTOMATED_ORDERS,
            "RiskPolicy": UNAPPROVED,
            "CostModel": COST_MODEL_INCOMPLETE,
            "BrokerCollection": BROKER_COLLECTION,
            "ExecutionAuthorization": EXECUTION_AUTHORIZATION,
            "order_send": ORDER_SEND,
            "BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
            "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
            "GenuineFills": GENUINE_FILLS,
        },
    }
