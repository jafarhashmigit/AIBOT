"""Phase 64.13 verdict."""

from __future__ import annotations

from typing import Any

from phase64_13.constants import (
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
    PHASE65,
    PRODUCTION_FINAL_ACTION,
    UNAPPROVED,
    VERDICT_BLOCKED,
    VERDICT_PARTIAL,
    VERDICT_VALIDATED,
)


def choose_verdict(
    *,
    defect_addressed: bool,
    close_only_independent: bool,
    entry_restrictions_ok: bool,
    monitoring_preserved: bool,
    boundary_ok: bool,
    lifecycle_ok: bool,
    evidence_freeze_ok: bool,
    risk_still_unapproved: bool,
    tests_ok: bool,
    adversarial_ok: bool,
    integrity_ok: bool,
    regressions_ok: bool,
) -> dict[str, Any]:
    ok = (
        defect_addressed
        and close_only_independent
        and entry_restrictions_ok
        and monitoring_preserved
        and boundary_ok
        and lifecycle_ok
        and evidence_freeze_ok
        and risk_still_unapproved
        and tests_ok
        and adversarial_ok
        and integrity_ok
        and regressions_ok
    )
    if ok:
        verdict = VERDICT_VALIDATED
        reason = (
            "CLOSE_ONLY is an independent session state; new entries rejected under "
            "CLOSE_ONLY/BREAK/CLOSED/UNKNOWN; internal paper-position monitoring preserved; "
            "UTC/PKT/DST boundaries pass; evidence freeze intact; no-order invariants hold"
        )
    elif close_only_independent or defect_addressed:
        verdict = VERDICT_PARTIAL
        reason = "Partial CLOSE_ONLY remediation; see failed gates"
    else:
        verdict = VERDICT_BLOCKED
        reason = "CLOSE_ONLY semantics not established"

    return {
        "verdict": verdict,
        "reason": reason,
        "gates": {
            "defect_addressed": defect_addressed,
            "close_only_independent": close_only_independent,
            "entry_restrictions_ok": entry_restrictions_ok,
            "monitoring_preserved": monitoring_preserved,
            "boundary_ok": boundary_ok,
            "lifecycle_ok": lifecycle_ok,
            "evidence_freeze_ok": evidence_freeze_ok,
            "risk_still_unapproved": risk_still_unapproved,
            "tests_ok": tests_ok,
            "adversarial_ok": adversarial_ok,
            "integrity_ok": integrity_ok,
            "regressions_ok": regressions_ok,
        },
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
            "Phase65": PHASE65,
        },
    }
