"""Trading-session model — do not invent from candle gaps."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from phase64_10.constants import (
    PHASE63_SESSIONS_PARTIAL,
    SESSION_MODEL_VERSION,
    UNKNOWN,
    canonical_json_sha256,
)


def build_session_model(*, live_api_sessions: Any = UNKNOWN) -> dict[str, Any]:
    """
    Live MT5 package used here does not expose symbol_info_session_*;
    symbol_info session_* fields are turnover stats, not weekly schedules.
    Phase63 user report is PARTIAL and not independently API-verified.
    """
    live_status = UNKNOWN
    if live_api_sessions not in (None, UNKNOWN, ""):
        live_status = "OBSERVED"
    else:
        live_api_sessions = UNKNOWN

    phase63 = dict(PHASE63_SESSIONS_PARTIAL)

    # Programmatic verification failed → UNKNOWN for execution gating
    verified_schedule = UNKNOWN
    completeness = "UNKNOWN"
    if phase63.get("completeness") == "PARTIAL" and live_status == UNKNOWN:
        completeness = "PARTIAL_USER_REPORTED_NOT_API_VERIFIED"

    out = {
        "session_model_version": SESSION_MODEL_VERSION,
        "programmatic_status": UNKNOWN,
        "completeness": completeness,
        "live_api_weekly_schedule": live_api_sessions,
        "live_api_note": (
            "MetaTrader5 Python package in this environment lacks symbol_info_session_quote/trade; "
            "symbol_info.session_* are intraday stats (open/close/turnover), not weekday schedules"
        ),
        "phase63_user_reported": phase63,
        "phase63_usable_as_broker_fact": False,
        "inferred_from_candle_gaps": False,
        "timezone": UNKNOWN,
        "dst_behavior": UNKNOWN,
        "rollover_maintenance_windows": UNKNOWN,
        "breaks": UNKNOWN,
        "conservative_execution_block_required": True,
        "rule": "If sessions cannot be verified programmatically, keep UNKNOWN and block future broker execution",
        "verified_schedule": verified_schedule,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def session_boundary_check(
    *,
    now_utc: datetime | None = None,
    sessions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed when schedule UNKNOWN/PARTIAL."""
    sessions = sessions or build_session_model()
    now_utc = now_utc or datetime.now(timezone.utc)
    if sessions.get("conservative_execution_block_required") or sessions.get("programmatic_status") == UNKNOWN:
        return {
            "in_session": UNKNOWN,
            "allowed": False,
            "reason": "session_schedule_unknown_or_unverified",
            "now_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    return {"in_session": True, "allowed": True, "reason": "ok"}


def rollover_window_check(*, weekday_utc: int | None = None) -> dict[str, Any]:
    """
    Triple-swap day is Wednesday (swap_rollover3days=3) per live symbol_info —
    but exact maintenance clock UNKNOWN without verified sessions.
    """
    return {
        "triple_swap_weekday_mt5": 3,
        "weekday_utc": weekday_utc,
        "rollover_clock": UNKNOWN,
        "allowed": False,
        "reason": "rollover_window_unknown_without_verified_sessions",
    }
