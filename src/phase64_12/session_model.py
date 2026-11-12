"""Timezone-aware session lookup — fail closed; never invent OPEN."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase64_12.applicability import build_applicability_matrix
from phase64_12.constants import (
    ACTIVE_SYMBOL,
    BREAK,
    BROKER_PUBLISHED_SESSION,
    CLOSED,
    OPEN,
    SESSION_MODEL_VERSION,
    UNKNOWN,
    UNKNOWN_SESSION,
    canonical_json_sha256,
)
from phase64_12.freshness import evaluate_conflict, freshness_policy
from phase64_12.schedule import build_verified_schedule_spec, state_at_utc


def build_session_model(
    *,
    applicable: bool | None = None,
    freshness: dict[str, Any] | None = None,
    conflict: bool = False,
    missing_schedule: bool = False,
) -> dict[str, Any]:
    appl = build_applicability_matrix()
    if applicable is None:
        applicable = bool(appl["applicability_justified"])
    fresh = freshness or freshness_policy()
    schedule = None if missing_schedule else build_verified_schedule_spec()

    programmatic = UNKNOWN
    evidence_kind = UNKNOWN_SESSION
    conservative_block = True
    verified = False

    if conflict:
        programmatic = UNKNOWN
        evidence_kind = BROKER_PUBLISHED_SESSION
        note = "Conflicting official sources — fail closed"
    elif missing_schedule or schedule is None:
        programmatic = UNKNOWN
        evidence_kind = UNKNOWN_SESSION
        note = "Missing schedule evidence — fail closed"
    elif not applicable:
        programmatic = UNKNOWN
        evidence_kind = BROKER_PUBLISHED_SESSION
        note = "Published schedule not applicable to exact symbol — retain UNKNOWN"
    elif not fresh.get("usable"):
        programmatic = UNKNOWN
        evidence_kind = BROKER_PUBLISHED_SESSION
        note = f"Evidence freshness status={fresh.get('status')} — fail closed"
    else:
        programmatic = "VERIFIED_SCHEDULE"
        evidence_kind = BROKER_PUBLISHED_SESSION
        conservative_block = False  # lookup can return OPEN/CLOSED/BREAK; OPEN ≠ authorize
        verified = True
        note = (
            "Authoritative Exness XAUUSD schedule applied to XAUUSDm via official Standard -m suffix mapping"
        )

    out = {
        "session_model_version": SESSION_MODEL_VERSION,
        "symbol": ACTIVE_SYMBOL,
        "programmatic_status": programmatic,
        "evidence_kind": evidence_kind,
        "verified": verified,
        "applicable": applicable,
        "freshness": fresh,
        "conflict": conflict,
        "schedule": schedule,
        "inferred_from_candle_gaps": False,
        "conservative_execution_block_required": conservative_block or not verified,
        "authorizes_execution": False,
        "note": note,
        "states": [OPEN, CLOSED, BREAK, UNKNOWN],
        "open_does_not_authorize_orders": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def lookup_session(
    ts: datetime,
    *,
    model: dict[str, Any] | None = None,
    honor_holidays: bool = True,
) -> dict[str, Any]:
    model = model or build_session_model()
    if model.get("conflict"):
        return {
            "state": UNKNOWN,
            "allowed_for_future_preflight": False,
            "reason": "conflicting_session_sources",
            "authorizes_execution": False,
        }
    if not model.get("verified") or model.get("conservative_execution_block_required"):
        return {
            "state": UNKNOWN,
            "allowed_for_future_preflight": False,
            "reason": "schedule_unverified_or_blocked",
            "authorizes_execution": False,
            "programmatic_status": model.get("programmatic_status"),
        }
    result = state_at_utc(ts, honor_holidays=honor_holidays)
    state = result["state"]
    allowed = state == OPEN
    return {
        **result,
        "allowed_for_future_preflight": allowed,
        "authorizes_execution": False,
        "preflight_action": (
            "REPORT_OPEN_NOT_AUTHORIZATION"
            if state == OPEN
            else ("REJECT" if state in (CLOSED, BREAK, UNKNOWN) else "REJECT")
        ),
        "symbol": ACTIVE_SYMBOL,
    }


def session_aware_preflight(
    *,
    now_utc: datetime | None = None,
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Research/DEMO preflight gate — never flips BROKER_EXECUTION_AUTHORIZED."""
    now_utc = now_utc or datetime.now(timezone.utc)
    look = lookup_session(now_utc, model=model)
    reject = look["state"] != OPEN
    return {
        "in_session": look["state"] == OPEN,
        "session_state": look["state"],
        "allowed": not reject and look.get("allowed_for_future_preflight") is True,
        "reject": reject,
        "reason": look.get("reason") or look.get("preflight_action"),
        "authorizes_execution": False,
        "now_utc": now_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detail": look,
    }


def conflict_demo() -> dict[str, Any]:
    a = [{"start": "00:00:00", "end": "21:58:00", "state": OPEN}]
    b = [{"start": "00:00:00", "end": "20:58:00", "state": OPEN}]
    return evaluate_conflict(source_a_segments=a, source_b_segments=b)
