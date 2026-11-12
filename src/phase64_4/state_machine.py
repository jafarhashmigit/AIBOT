"""Fail-closed broker execution state machine — design + transition validation only."""

from __future__ import annotations

from typing import Any

from phase64_4.constants import (
    EXECUTION_STATES,
    STATE_MACHINE_VERSION,
    TERMINAL_STATES,
    canonical_json_sha256,
)

# Allowed transitions. Anything not listed is fail-closed.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset(
        {
            "VALIDATED",
            "BLOCKED_BY_RISK",
            "BLOCKED_BY_AUTHORIZATION",
            "CANCELLED",
            "UNKNOWN_REQUIRES_RECONCILIATION",  # conflicting evidence / incident
        }
    ),
    "VALIDATED": frozenset(
        {
            "AUTHORIZED",
            "BLOCKED_BY_RISK",
            "BLOCKED_BY_AUTHORIZATION",
            "CANCELLED",
            "UNKNOWN_REQUIRES_RECONCILIATION",
        }
    ),
    "AUTHORIZED": frozenset(
        {
            "SUBMISSION_PENDING",
            "BLOCKED_BY_AUTHORIZATION",  # kill switch / revoke
            "CANCELLED",
            "EXPIRED",
            "UNKNOWN_REQUIRES_RECONCILIATION",
        }
    ),
    "SUBMISSION_PENDING": frozenset(
        {
            "ACKNOWLEDGED",
            "REJECTED",
            "UNKNOWN_REQUIRES_RECONCILIATION",  # timeout / missing ack
            "CANCELLED",
            "EXPIRED",
        }
    ),
    "ACKNOWLEDGED": frozenset(
        {
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELLED",
            "EXPIRED",
            "UNKNOWN_REQUIRES_RECONCILIATION",
        }
    ),
    "PARTIALLY_FILLED": frozenset(
        {
            "PARTIALLY_FILLED",  # additional partial
            "FILLED",
            "CANCELLED",
            "EXPIRED",
            "UNKNOWN_REQUIRES_RECONCILIATION",
        }
    ),
    "UNKNOWN_REQUIRES_RECONCILIATION": frozenset(
        {
            "ACKNOWLEDGED",
            "PARTIALLY_FILLED",
            "FILLED",
            "REJECTED",
            "CANCELLED",
            "EXPIRED",
            "UNKNOWN_REQUIRES_RECONCILIATION",  # repeated recon
        }
    ),
    # Terminals: no outbound
    "FILLED": frozenset(),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
    "EXPIRED": frozenset(),
    "BLOCKED_BY_RISK": frozenset(),
    "BLOCKED_BY_AUTHORIZATION": frozenset(),
}


class ExecutionStateError(RuntimeError):
    pass


class BrokerExecutionStateMachine:
    """In-memory FSM for design validation. Never submits orders."""

    def __init__(self, *, execution_request_id: str, initial: str = "CREATED"):
        if initial not in EXECUTION_STATES:
            raise ExecutionStateError(f"bad_initial:{initial}")
        self.execution_request_id = execution_request_id
        self.state = initial
        self.history: list[dict[str, Any]] = [
            {"from": None, "to": initial, "reason": "init", "submission_attempted": False}
        ]
        self.incident_raised = False
        self.broker_order_id: str | None = None
        self.submission_count = 0
        self.seen_deal_ids: set[str] = set()
        self.fill_log: list[dict[str, Any]] = []

    def transition(self, new_state: str, *, reason: str) -> dict[str, Any]:
        if new_state not in EXECUTION_STATES:
            raise ExecutionStateError(f"unknown_state:{new_state}")
        allowed = ALLOWED_TRANSITIONS.get(self.state, frozenset())
        if new_state not in allowed:
            self.incident_raised = True
            raise ExecutionStateError(f"illegal_transition:{self.state}->{new_state}")
        if self.state in TERMINAL_STATES:
            self.incident_raised = True
            raise ExecutionStateError(f"terminal_locked:{self.state}")
        prev = self.state
        self.state = new_state
        rec = {
            "from": prev,
            "to": new_state,
            "reason": reason,
            "submission_attempted": False,
        }
        self.history.append(rec)
        return rec

    def mark_submission_pending(self, *, reason: str = "authorized_submit") -> dict[str, Any]:
        """
        Enter SUBMISSION_PENDING. Phase64.4 records the transition only —
        does NOT call order_send. A second call without a new execution_request_id is forbidden.
        """
        if self.submission_count >= 1 and self.state in (
            "SUBMISSION_PENDING",
            "ACKNOWLEDGED",
            "PARTIALLY_FILLED",
            "FILLED",
            "UNKNOWN_REQUIRES_RECONCILIATION",
        ):
            self.incident_raised = True
            raise ExecutionStateError("resubmit_forbidden_same_execution_request")
        rec = self.transition("SUBMISSION_PENDING", reason=reason)
        self.submission_count += 1
        rec["submission_attempted"] = False  # design-only: never true in 64.4
        rec["phase64_4_note"] = "transition_recorded_without_broker_call"
        return rec

    def on_timeout_without_ack(self) -> dict[str, Any]:
        return self.transition(
            "UNKNOWN_REQUIRES_RECONCILIATION",
            reason="timeout_missing_ack_must_reconcile_not_resubmit",
        )

    def ingest_deal(self, *, deal_id: str, price: float, volume: float, remaining: float) -> dict[str, Any]:
        if deal_id in self.seen_deal_ids:
            raise ExecutionStateError(f"duplicate_deal:{deal_id}")
        for f in self.fill_log:
            if f["deal_id"] == deal_id:
                raise ExecutionStateError(f"duplicate_deal:{deal_id}")
        self.seen_deal_ids.add(deal_id)
        self.fill_log.append({"deal_id": deal_id, "price": price, "volume": volume})
        if self.state == "SUBMISSION_PENDING":
            self.transition("ACKNOWLEDGED", reason="deal_implies_ack_pending_recon")
        if remaining > 0:
            if self.state == "ACKNOWLEDGED":
                self.transition("PARTIALLY_FILLED", reason="partial_fill")
            elif self.state == "PARTIALLY_FILLED":
                self.transition("PARTIALLY_FILLED", reason="additional_partial")
            else:
                self.transition("PARTIALLY_FILLED", reason="partial_fill")
        else:
            self.transition("FILLED", reason="fully_filled")
        return {"state": self.state, "n_deals": len(self.seen_deal_ids)}

    def raise_conflict_incident(self, *, reason: str) -> None:
        self.incident_raised = True
        if self.state not in TERMINAL_STATES and self.state != "UNKNOWN_REQUIRES_RECONCILIATION":
            try:
                self.transition("UNKNOWN_REQUIRES_RECONCILIATION", reason=f"incident:{reason}")
            except ExecutionStateError:
                pass


def state_machine_spec() -> dict[str, Any]:
    return {
        "version": STATE_MACHINE_VERSION,
        "states": list(EXECUTION_STATES),
        "terminal_states": sorted(TERMINAL_STATES),
        "allowed_transitions": {k: sorted(v) for k, v in ALLOWED_TRANSITIONS.items()},
        "rules": [
            "No submission without AUTHORIZED",
            "No retry that creates a second broker order on the same execution_request_id",
            "Timeout → UNKNOWN_REQUIRES_RECONCILIATION, never blind resubmit",
            "Partial fills update exposure (caller responsibility) before further risk checks",
            "Duplicate broker deals rejected",
            "Conflicting evidence → incident + halt",
            "Kill switch forces BLOCKED_BY_AUTHORIZATION for new requests",
            "Every transition append-only auditable in history",
        ],
        "phase64_4_submission_disabled": True,
    }


def audit_state_machine() -> dict[str, Any]:
    sm = BrokerExecutionStateMachine(execution_request_id="er_test")
    sm.transition("VALIDATED", reason="schema_ok")
    sm.transition("AUTHORIZED", reason="gates_pass_design")
    sm.mark_submission_pending()
    timed = sm.on_timeout_without_ack()
    # illegal resubmit
    resubmit_blocked = False
    try:
        sm2 = BrokerExecutionStateMachine(execution_request_id="er_test2")
        sm2.transition("VALIDATED", reason="ok")
        sm2.transition("AUTHORIZED", reason="ok")
        sm2.mark_submission_pending()
        sm2.mark_submission_pending()
    except ExecutionStateError:
        resubmit_blocked = True
    # illegal skip AUTHORIZED
    skip_blocked = False
    try:
        sm3 = BrokerExecutionStateMachine(execution_request_id="er3")
        sm3.transition("SUBMISSION_PENDING", reason="illegal")
    except ExecutionStateError:
        skip_blocked = True
    # partial then fill
    sm4 = BrokerExecutionStateMachine(execution_request_id="er4")
    for s in ("VALIDATED", "AUTHORIZED"):
        sm4.transition(s, reason="ok")
    sm4.mark_submission_pending()
    sm4.transition("ACKNOWLEDGED", reason="ack")
    sm4.ingest_deal(deal_id="d1", price=2650.1, volume=0.01, remaining=0.01)
    dup = False
    try:
        sm4.ingest_deal(deal_id="d1", price=2650.1, volume=0.01, remaining=0.01)
    except ExecutionStateError:
        dup = True
    sm4.ingest_deal(deal_id="d2", price=2650.2, volume=0.01, remaining=0.0)
    out = {
        "spec": state_machine_spec(),
        "timeout_to_recon": timed["to"] == "UNKNOWN_REQUIRES_RECONCILIATION",
        "resubmit_blocked": resubmit_blocked,
        "skip_authorized_blocked": skip_blocked,
        "duplicate_deal_blocked": dup,
        "final_filled": sm4.state == "FILLED",
        "pass": all(
            [
                timed["to"] == "UNKNOWN_REQUIRES_RECONCILIATION",
                resubmit_blocked,
                skip_blocked,
                dup,
                sm4.state == "FILLED",
            ]
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
