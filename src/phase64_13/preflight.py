"""Preflight separation — entry vs monitoring vs broker availability vs auth."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase64_13.constants import (
    BREAK,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CLOSE_ONLY,
    CLOSED,
    OPEN,
    UNKNOWN,
    canonical_json_sha256,
)
from phase64_13.schedule import state_at_utc


def evaluate_session_gates(
    ts: datetime,
    *,
    honor_holidays: bool = True,
    force_state: str | None = None,
) -> dict[str, Any]:
    """
    A. New-position entry eligibility
    B. Existing-position management eligibility (internal)
    C. Broker operation availability (unknown/unguaranteed)
    D. Overall execution authorization (independent — always blocked here)
    """
    if force_state is not None:
        look = {"state": force_state, "reason": "forced_fixture", "utc": None, "pkt": None}
    else:
        look = state_at_utc(ts, honor_holidays=honor_holidays)
    state = look["state"]

    new_entry_ok = state == OPEN
    # Internal monitoring always enabled regardless of session
    internal_monitoring = True
    # Broker operation availability is NOT proven by schedule alone
    broker_ops_available = UNKNOWN
    # Independent authorization gate — never flipped by session
    exec_auth = BROKER_EXECUTION_AUTHORIZED
    submission = BROKER_SUBMISSION_ENABLED

    out = {
        "session_state": state,
        "A_new_entry_eligible": new_entry_ok,
        "A_new_entry_action": "PERMIT_SESSION_CHECK" if new_entry_ok else "REJECT",
        "B_internal_position_monitoring": internal_monitoring,
        "C_broker_operation_availability": broker_ops_available,
        "C_note": "Schedule does not guarantee broker will accept any operation",
        "D_execution_authorization": exec_auth,
        "D_submission_enabled": submission,
        "reject_new_entry": not new_entry_ok,
        "authorizes_execution": False,
        "lookup": look,
        "states_checked": {
            "is_open": state == OPEN,
            "is_close_only": state == CLOSE_ONLY,
            "is_break": state == BREAK,
            "is_closed": state == CLOSED,
            "is_unknown": state == UNKNOWN,
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def session_aware_entry_preflight(ts: datetime | None = None) -> dict[str, Any]:
    ts = ts or datetime.now(timezone.utc)
    g = evaluate_session_gates(ts)
    return {
        "session_permits_entry_check": g["A_new_entry_eligible"],
        "reject_new_entry": g["reject_new_entry"],
        "overall_execution_blocked": True,
        "reject_live_submission": True,
        "authorizes_execution": False,
        "reason": (
            "execution_authorization_blocked"
            if g["A_new_entry_eligible"]
            else f"session_{g['session_state'].lower()}_rejects_new_entry"
        ),
        "gates": g,
    }
