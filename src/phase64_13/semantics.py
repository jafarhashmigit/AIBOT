"""Canonical session-state semantics and eligibility matrix."""

from __future__ import annotations

from typing import Any

from phase64_13.constants import (
    BREAK,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    CLOSE_ONLY,
    CLOSED,
    OPEN,
    SESSION_SEMANTICS_VERSION,
    SESSION_STATES,
    UNKNOWN,
    canonical_json_sha256,
)


def canonical_semantics() -> dict[str, Any]:
    rows = [
        {
            "state": OPEN,
            "new_entry": "PERMIT_SESSION_GATE",
            "internal_position_monitoring": "ENABLED",
            "execution_authorization": "INDEPENDENT_GATE",
            "meaning": "New entries may pass session-state check; other gates still apply",
        },
        {
            "state": CLOSE_ONLY,
            "new_entry": "REJECT",
            "internal_position_monitoring": "ENABLED",
            "execution_authorization": "INDEPENDENT_GATE",
            "meaning": (
                "New entries rejected; internal existing-position management remains available; "
                "broker close acceptance not guaranteed"
            ),
        },
        {
            "state": BREAK,
            "new_entry": "REJECT",
            "internal_position_monitoring": "ENABLED",
            "execution_authorization": "INDEPENDENT_GATE",
            "meaning": "Intraday pause; not equated to CLOSED or CLOSE_ONLY",
        },
        {
            "state": CLOSED,
            "new_entry": "REJECT",
            "internal_position_monitoring": "ENABLED",
            "execution_authorization": "INDEPENDENT_GATE",
            "meaning": "Weekly/daily closure; never assume broker accepts operations",
        },
        {
            "state": UNKNOWN,
            "new_entry": "REJECT",
            "internal_position_monitoring": "ENABLED",
            "execution_authorization": "INDEPENDENT_GATE",
            "meaning": "Fail closed for new entries; monitoring preserved",
        },
    ]
    out = {
        "semantics_version": SESSION_SEMANTICS_VERSION,
        "states": list(SESSION_STATES),
        "states_distinct": len(set(SESSION_STATES)) == len(SESSION_STATES),
        "rows": rows,
        "broker_submission_enabled": BROKER_SUBMISSION_ENABLED,
        "broker_execution_authorized": BROKER_EXECUTION_AUTHORIZED,
        "session_never_overrides_auth_gate": True,
        "close_only_ne_break": CLOSE_ONLY != BREAK,
        "break_ne_closed": BREAK != CLOSED,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
