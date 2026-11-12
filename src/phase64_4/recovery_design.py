"""Crash recovery & reconciliation design — discover broker state before acting."""

from __future__ import annotations

from typing import Any

from phase64_4.constants import canonical_json_sha256


CRASH_BOUNDARIES = (
    "before_authorization",
    "after_authorization_before_submission",
    "during_submission",
    "after_broker_accept_before_local_ack_persist",
    "after_partial_fill",
    "after_full_fill_before_local_persist",
    "during_cancellation",
    "during_reconciliation",
)


def recovery_matrix() -> list[dict[str, Any]]:
    """
    For each crash boundary: local observation, broker discovery requirement, next action.
    Critical rule: missing local acknowledgement ≠ broker rejection.
    """
    return [
        {
            "boundary": "before_authorization",
            "local": "execution_request CREATED/VALIDATED only",
            "broker_discovery": "NONE required — nothing submitted",
            "next_action": "Resume authorization gates; do not create duplicate request for same attempt key",
            "resubmit": False,
        },
        {
            "boundary": "after_authorization_before_submission",
            "local": "AUTHORIZED; submission_count=0",
            "broker_discovery": "Query open orders/deals by magic/comment/linkage when RO history APIs authorized; else manual CSV",
            "next_action": "If no broker order → may enter SUBMISSION_PENDING once; if order found → attach broker_order_id and ACKNOWLEDGE",
            "resubmit": "ONLY if broker discovery confirms absence",
        },
        {
            "boundary": "during_submission",
            "local": "SUBMISSION_PENDING or crash mid-call",
            "broker_discovery": "MANDATORY before any retry",
            "next_action": "UNKNOWN_REQUIRES_RECONCILIATION until broker order presence known",
            "resubmit": False,
            "rule": "Never assume reject on missing local ack",
        },
        {
            "boundary": "after_broker_accept_before_local_ack_persist",
            "local": "missing ACK record; broker may hold order",
            "broker_discovery": "Find broker_order_id; persist BROKER_ORDER_ACKNOWLEDGEMENT from raw evidence",
            "next_action": "ACKNOWLEDGED then continue fill monitoring",
            "resubmit": False,
        },
        {
            "boundary": "after_partial_fill",
            "local": "PARTIALLY_FILLED with subset of deals",
            "broker_discovery": "List all deals for broker_order_id; idempotent ingest by deal_id",
            "next_action": "Update exposure; do not open duplicate position locally",
            "resubmit": False,
        },
        {
            "boundary": "after_full_fill_before_local_persist",
            "local": "fills may be incomplete locally",
            "broker_discovery": "Confirm deals + position; persist fills then FILLED",
            "next_action": "Idempotent fill ingest; link experience only after durable persist",
            "resubmit": False,
        },
        {
            "boundary": "during_cancellation",
            "local": "cancel requested",
            "broker_discovery": "Confirm order cancelled vs filled during cancel race",
            "next_action": "If filled during cancel → FILLED + incident note; else CANCELLED",
            "resubmit": False,
        },
        {
            "boundary": "during_reconciliation",
            "local": "UNKNOWN_REQUIRES_RECONCILIATION",
            "broker_discovery": "Repeat-safe recon; identical inputs → no extra records",
            "next_action": "Resolve to ACK/FILL/REJECT/CANCEL only from broker evidence",
            "resubmit": False,
        },
    ]


def broker_discovery_procedure() -> dict[str, Any]:
    return {
        "principle": "Discover whether an order exists at the broker BEFORE deciding next transition",
        "interim_without_history_api": [
            "Manual MT5 Toolbox → History → Orders/Deals export (CSV) for XAUUSDm",
            "Match by time window + volume + side + comment/magic if used",
            "Store immutable raw export sha256 as raw_broker_evidence",
        ],
        "future_after_allowlist_review": [
            "RO orders_get / history_orders_get / history_deals_get — REQUIRES separate security review",
            "NOT enabled in Phase64.4",
        ],
        "missing_local_ack_means": "UNKNOWN_REQUIRES_RECONCILIATION — never REJECTED by assumption",
        "idempotent_recon": "Repeated reconciliation with same evidence produces no additional fills/deals",
        "conflict_policy": "Conflicting prices/volumes for same deal_id → incident + halt submissions",
    }


def audit_recovery_design() -> dict[str, Any]:
    matrix = recovery_matrix()
    during = next(r for r in matrix if r["boundary"] == "during_submission")
    out = {
        "boundaries": list(CRASH_BOUNDARIES),
        "matrix": matrix,
        "broker_discovery": broker_discovery_procedure(),
        "covers_all_boundaries": [r["boundary"] for r in matrix] == list(CRASH_BOUNDARIES),
        "no_blind_resubmit_on_timeout": during["resubmit"] is False,
        "missing_ack_not_reject": True,
        "pass": len(matrix) == len(CRASH_BOUNDARIES) and during["resubmit"] is False,
        "evidence_type": "DESIGN_SPEC",
        "runtime_crash_tests": "NOT RUN — design phase; no broker adapter",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
