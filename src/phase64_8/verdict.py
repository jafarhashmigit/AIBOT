"""Phase 64.8 multi-dimension verdict."""

from __future__ import annotations

from typing import Any

from phase64_8.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    BROKER_EXECUTION_READY,
    CHAMPION_STATUS,
    LIVE_TRADING,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    UNAPPROVED,
)


def choose_verdict(
    *,
    approval: dict[str, Any],
    live: dict[str, Any],
    recon: dict[str, Any],
    adversarial: dict[str, Any],
    security: dict[str, Any],
    integrity: dict[str, Any],
    tests_ok: bool,
    regressions_ok: bool,
) -> dict[str, Any]:
    api_ok = bool(approval.get("pass"))
    live_ok = live.get("status") == "COLLECTED"
    journal_ok = bool((live.get("journal_integrity") or {}).get("index_matches", False)) if live_ok else False
    idem = live_ok  # reinforced by adversarial replay/dup cases
    adv_ok = bool(adversarial.get("suite_pass"))
    sec_ok = bool(security.get("pass"))
    integ_ok = bool(integrity.get("checks_pass"))

    # Fill recon explicitly not claimed when no genuine trade deals
    n_trade = int(live.get("n_trade_deals") or 0) if live_ok else 0
    fill_recon = "NOT_VALIDATED_ZERO_GENUINE_TRADE_DEALS" if n_trade == 0 else "OBSERVED"
    pos_recon = "VALIDATED_EMPTY" if live_ok and int(live.get("n_positions") or 0) == 0 else (
        "OBSERVED" if live_ok else "BLOCKED"
    )
    order_recon = "VALIDATED_EMPTY" if live_ok and int(live.get("n_open_orders") or 0) == 0 else (
        "OBSERVED" if live_ok else "BLOCKED"
    )
    deal_recon = (
        "BALANCE_ONLY_FILL_RECON_NOT_VALIDATED"
        if live_ok and n_trade == 0
        else ("OBSERVED" if live_ok else "BLOCKED")
    )
    cost_complete = "INCOMPLETE"  # sessions/commission schedule still unknown; no fill costs validated

    dimensions = {
        "api_approval_status": "APPROVED_READ_ONLY" if api_ok else "BLOCKED",
        "live_broker_evidence_collection": "PASS" if live_ok else "BLOCKED",
        "position_reconciliation": pos_recon,
        "order_reconciliation": order_recon,
        "deal_reconciliation": deal_recon,
        "fill_reconciliation": fill_recon,
        "journal_durability": "PASS" if journal_ok else "BLOCKED",
        "idempotency": "PASS" if idem and adv_ok else "BLOCKED",
        "cost_evidence_completeness": cost_complete,
        "risk_policy": UNAPPROVED,
        "execution_authorization": LIVE_TRADING,
    }

    core = api_ok and live_ok and journal_ok and adv_ok and sec_ok and integ_ok and tests_ok and regressions_ok
    if core and not BROKER_EXECUTION_READY and ORDER_SEND == "PROHIBITED":
        verdict = "BROKER_RO_RECONCILIATION_VALIDATED"
        reason = (
            "RO allowlist approved; live evidence collection + empty pos/order validation + "
            "journal durability/idempotency/adversarial pass; fill recon not claimed (0 trade deals)"
        )
    elif api_ok and (live_ok or adv_ok):
        verdict = "BROKER_RO_RECONCILIATION_PARTIAL"
        reason = "Partial RO reconciliation capability; see failed dimensions"
    else:
        verdict = "BROKER_RO_RECONCILIATION_BLOCKED"
        reason = "Critical RO reconciliation blockers remain"

    return {
        "verdict": verdict,
        "reason": reason,
        "dimensions": dimensions,
        "invariants": {
            "Champion": CHAMPION_STATUS,
            "Production": PRODUCTION_FINAL_ACTION,
            "Live": LIVE_TRADING,
            "AutomatedOrders": AUTOMATED_ORDERS,
            "RiskPolicy": UNAPPROVED,
            "BrokerCollection": BROKER_COLLECTION,
            "order_send": ORDER_SEND,
            "BrokerExecutionReady": BROKER_EXECUTION_READY,
            "Phase65": "NOT_STARTED",
        },
    }
