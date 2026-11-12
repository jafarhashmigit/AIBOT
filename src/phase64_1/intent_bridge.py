"""Bridge Phase64 intent journal — one intent per canonical decision; non-executable for WAIT/reject."""

from __future__ import annotations

from typing import Any

from phase64.execution_intent import ExecutionIntentJournal, create_execution_intent
from phase64_1.market_snapshot import CrashInjected


EXECUTABLE_STATUSES = frozenset({"PENDING", "ORDER_LINKED", "PARTIAL_FILL", "FILLED", "UNFILLED"})


def ensure_execution_intent(
    journal: ExecutionIntentJournal,
    *,
    decision: dict[str, Any],
    risk: dict[str, Any],
    account_profile: dict[str, Any] | None = None,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """
    Idempotent: at most one intent per canonical decision_id.
    WAIT / risk-reject → non-executable statuses only.
    BUY/SELL after risk approval → PENDING (paper path; broker_submission DISABLED).
    """
    decision_id = str(decision["decision_id"])
    existing = journal.intents_for_decision(decision_id)
    if existing:
        # Prefer the first persisted intent; never create a second independent intent
        intent = existing[0]
        return {
            "intent_id": intent.get("intent_id"),
            "decision_id": decision_id,
            "intent_status": intent.get("intent_status"),
            "reused": True,
            "executable": intent.get("intent_status") in EXECUTABLE_STATUSES,
            "record": intent,
        }

    if crash_at == "before_intent_persistence":
        raise CrashInjected("before_intent_persistence")

    # Temporarily align journal crash gates if needed
    prev = journal.crash_at
    if crash_at == "after_intent_before_paper_entry":
        journal.crash_at = None  # persist fully; engine raises after return
    try:
        created = create_execution_intent(
            journal,
            decision=decision,
            risk=risk,
            account_profile=account_profile,
        )
    finally:
        journal.crash_at = prev

    status = created["intent_status"]
    return {
        "intent_id": created["intent_id"],
        "decision_id": decision_id,
        "intent_status": status,
        "reused": False,
        "executable": status in EXECUTABLE_STATUSES,
        "record": created.get("record"),
    }


def link_intent_outcome(
    journal: ExecutionIntentJournal,
    *,
    decision_id: str,
    intent_id: str,
    position_id: str | None,
    txn_id: str | None,
    net_r: float | None,
    exit_reason: str | None,
) -> dict[str, Any]:
    return journal.commit(
        stage="OUTCOME_RECORDED",
        decision_id=decision_id,
        intent_id=intent_id,
        intent_status=None,
        payload={
            "position_id": position_id,
            "txn_id": txn_id,
            "net_r": net_r,
            "exit_reason": exit_reason,
            "broker_order_send": False,
        },
    )


def link_intent_experience(
    journal: ExecutionIntentJournal,
    *,
    decision_id: str,
    intent_id: str,
    experience_id: str | None,
) -> dict[str, Any]:
    return journal.commit(
        stage="EXPERIENCE_LINKED",
        decision_id=decision_id,
        intent_id=intent_id,
        payload={"experience_id": experience_id, "broker_order_send": False},
    )
