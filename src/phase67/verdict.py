"""Phase 67 verdict selection."""

from __future__ import annotations

from typing import Any

from phase67.constants import (
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
    VERDICT_BLOCKED,
    VERDICT_EXPLORATORY,
    VERDICT_INSUFFICIENT,
    VERDICT_INTEGRITY,
    VERDICT_OPS_READY,
)


def choose_verdict(
    *,
    security_ok: bool,
    integrity_ok: bool,
    exploratory_ok: bool,
    ops_design_ok: bool,
    verify_runtime: dict[str, Any] | None,
    live_dates: int,
    live_m5: int,
    live_quotes: int,
    tests_ok: bool,
) -> dict[str, Any]:
    vr = verify_runtime or {}
    measured = float(vr.get("runtime_sec_measured") or 0)
    ingested = int((vr.get("totals") or {}).get("INGESTED") or 0)

    if not integrity_ok:
        verdict, reason = VERDICT_INTEGRITY, "Integrity checks failed"
    elif not security_ok or not tests_ok:
        verdict, reason = VERDICT_BLOCKED, "Security or tests blocked collection"
    elif ops_design_ok and measured > 0 and ingested >= 0 and live_dates < 5:
        # Engineering + measured verify run, but live evidence still insufficient for research
        verdict = VERDICT_INSUFFICIENT
        reason = (
            f"Collector ops verified (measured_runtime_sec={measured}, verify_ingested={ingested}); "
            f"exploratory archive analysis complete={exploratory_ok}; "
            f"live Exness dates={live_dates} m5={live_m5} quotes={live_quotes} still insufficient "
            "for Exness-native discovery. Not a continuous-uptime claim."
        )
    elif ops_design_ok and live_dates >= 5 and live_m5 >= 500:
        verdict = VERDICT_OPS_READY
        reason = "Exness collection operationally ready with meaningful live depth"
    elif exploratory_ok and not ops_design_ok:
        verdict = VERDICT_EXPLORATORY
        reason = "Exploratory research complete; collection not operational"
    else:
        verdict = VERDICT_BLOCKED
        reason = "Collection not ready"

    return {
        "verdict": verdict,
        "reason": reason,
        "engineering_ops_ready": ops_design_ok and security_ok and tests_ok,
        "exploratory_complete": exploratory_ok,
        "live_evidence_sufficient_for_discovery": False,
        "measured_verify_runtime_sec": measured,
        "verify_ingested": ingested,
        "continuous_uptime_claimed": False,
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
