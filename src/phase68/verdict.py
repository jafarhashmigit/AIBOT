"""Phase 68 verdict — may report primary + secondary distinctions."""

from __future__ import annotations

from typing import Any

from phase68.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CHAMPION_STATUS,
    COMMISSION_UNKNOWN,
    COST_MODEL_INCOMPLETE,
    EXECUTION_AUTHORIZATION,
    GENUINE_FILLS,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    SWAP_UNKNOWN,
    UNAPPROVED,
    VERDICT_BEHAVIOUR,
    VERDICT_INSUFFICIENT,
    VERDICT_LIVE_FAIL,
    VERDICT_LIVE_OK,
)


def choose_verdict(
    *,
    n_events: int,
    n_dates: int,
    live_integrity_ok: bool,
    security_ok: bool,
    exploratory_complete: bool,
) -> dict[str, Any]:
    # Sample sufficiency for claiming identifiable behaviour patterns (descriptive)
    behaviour_ok = exploratory_complete and n_events >= 20 and n_dates >= 10
    sample_weak = n_events < 30 or n_dates < 15

    secondary = []
    if live_integrity_ok:
        secondary.append(VERDICT_LIVE_OK)
    else:
        secondary.append(VERDICT_LIVE_FAIL)

    if not security_ok:
        primary = VERDICT_LIVE_FAIL
        reason = "Security/integrity blocked"
    elif not live_integrity_ok:
        primary = VERDICT_LIVE_FAIL
        reason = "Live collection integrity failed (backfill/new separation or tick policy)"
    elif behaviour_ok and sample_weak:
        primary = VERDICT_INSUFFICIENT
        reason = (
            f"Exploratory displacement patterns computed (n_events={n_events}, n_dates={n_dates}) "
            "but sample too small for strong behavioural claims; live integrity verified separately."
        )
        secondary = [VERDICT_LIVE_OK, VERDICT_BEHAVIOUR]
    elif behaviour_ok:
        primary = VERDICT_BEHAVIOUR
        reason = (
            f"Exploratory displacement response behaviour identified on consumed archive "
            f"(n_events={n_events}, n_dates={n_dates}); NOT independent discovery. "
            f"Live integrity: {VERDICT_LIVE_OK}."
        )
    else:
        primary = VERDICT_INSUFFICIENT
        reason = f"Insufficient sample or incomplete exploratory (n_events={n_events}, n_dates={n_dates})"

    return {
        "verdict": primary,
        "secondary_verdicts": secondary,
        "reason": reason,
        "n_events": n_events,
        "n_dates": n_dates,
        "live_collection_integrity_verified": live_integrity_ok,
        "independent_discovery": False,
        "champion_promotion": False,
        "invariants": {
            "Champion": CHAMPION_STATUS,
            "Production": PRODUCTION_FINAL_ACTION,
            "Live": LIVE_TRADING,
            "AutomatedOrders": AUTOMATED_ORDERS,
            "RiskPolicy": UNAPPROVED,
            "CostModel": COST_MODEL_INCOMPLETE,
            "Commission": COMMISSION_UNKNOWN,
            "Swap": SWAP_UNKNOWN,
            "BrokerCollection": BROKER_COLLECTION,
            "ExecutionAuthorization": EXECUTION_AUTHORIZATION,
            "order_send": ORDER_SEND,
            "BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
            "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
            "GenuineFills": GENUINE_FILLS,
        },
    }
