"""Phase 66 verdict."""

from __future__ import annotations

from typing import Any

from phase66.constants import (
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
    MARGIN_INCOMPLETE,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    SWAP_UNKNOWN,
    UNAPPROVED,
    VERDICT_ENGINEERING,
    VERDICT_INSUFFICIENT,
    VERDICT_OPS,
    VERDICT_QUALITY,
)


def choose_verdict(
    *,
    engineering_ok: bool,
    security_ok: bool,
    fixture_collection_ok: bool,
    quality_blocked: bool,
    ops_blocked: bool,
    independent_evidence_sufficient: bool,
    live_genuine_n: int,
    tests_ok: bool,
    regressions_ok: bool,
) -> dict[str, Any]:
    if quality_blocked:
        verdict = VERDICT_QUALITY
        reason = "Data quality gates blocked collection readiness"
    elif ops_blocked and not fixture_collection_ok:
        verdict = VERDICT_OPS
        reason = "Collection operationally blocked"
    elif engineering_ok and security_ok and fixture_collection_ok and tests_ok and regressions_ok:
        # Primary Phase66 deliverable is engineering readiness; research sufficiency is reported separately.
        verdict = VERDICT_ENGINEERING
        if independent_evidence_sufficient:
            reason = "Collector engineering ready and independent evidence sufficient"
        else:
            reason = (
                "COLLECTION_ENGINEERING_READY: fixture+live RO path, durability, quality, session awareness, "
                f"and security pass; independent research evidence still insufficient "
                f"(live_genuine_ingested={live_genuine_n}). Not a continuous-collection uptime claim."
            )
    elif not tests_ok or not regressions_ok or not security_ok:
        verdict = VERDICT_OPS
        reason = "Tests, regressions, or security blocked operational readiness"
    elif not independent_evidence_sufficient and engineering_ok:
        verdict = VERDICT_INSUFFICIENT
        reason = "Engineering partial; independent evidence insufficient"
    else:
        verdict = VERDICT_OPS
        reason = "Collection not operationally ready"

    return {
        "verdict": verdict,
        "reason": reason,
        "engineering_ready": engineering_ok and fixture_collection_ok and security_ok and tests_ok,
        "independent_research_evidence_sufficient": independent_evidence_sufficient,
        "live_genuine_observations_ingested": live_genuine_n,
        "continuous_collection_uptime_claimed": False,
        "invariants": {
            "Champion": CHAMPION_STATUS,
            "Production": PRODUCTION_FINAL_ACTION,
            "Live": LIVE_TRADING,
            "AutomatedOrders": AUTOMATED_ORDERS,
            "RiskPolicy": UNAPPROVED,
            "CostModel": COST_MODEL_INCOMPLETE,
            "Commission": COMMISSION_UNKNOWN,
            "Swap": SWAP_UNKNOWN,
            "Margin": MARGIN_INCOMPLETE,
            "BrokerCollection": BROKER_COLLECTION,
            "ExecutionAuthorization": EXECUTION_AUTHORIZATION,
            "order_send": ORDER_SEND,
            "BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
            "BROKER_EXECUTION_AUTHORIZED": BROKER_EXECUTION_AUTHORIZED,
            "GenuineFills": GENUINE_FILLS,
        },
    }
