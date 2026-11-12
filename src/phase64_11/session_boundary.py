"""Trading-session evidence boundary — no candle-gap inference."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE,
    UNKNOWN,
    USER_REPORTED,
    canonical_json_sha256,
)


def investigate_session_boundary() -> dict[str, Any]:
    live_api = {
        "weekly_schedule_via_permitted_api": UNKNOWN,
        "symbol_info_session_star_are_stats_not_schedule": True,
        "python_mt5_session_apis_present": False,
        "evidence_type": UNKNOWN,
        "note": (
            "This environment's MetaTrader5 package exposes no symbol_info_session_quote/trade. "
            "symbol_info.session_* fields are intraday turnover/open/close stats, not weekday schedules."
        ),
    }
    phase63 = {
        "completeness": "PARTIAL",
        "evidence_type": USER_REPORTED,
        "usable_as_broker_fact": False,
        "truncated_fields": ["monday_to_thursday.segment_2_end"],
        "timezone": UNKNOWN,
        "dst": UNKNOWN,
        "inferred_from_candle_gaps": False,
    }
    external = {
        "in_repo_authoritative_session_doc": False,
        "external_exness_hours_potentially_available": True,
        "verified_and_mapped_to_xauusdm_trial15": False,
        "evidence_type": UNKNOWN,
        "note": (
            "Exness may publish metal trading hours externally. That path is "
            "CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE only after a verified, dated, "
            "instrument-applicable citation is ingested — not assumed in this phase."
        ),
    }

    classification = CLOSABLE_FROM_AUTHORITATIVE_EXTERNAL_EVIDENCE
    reasoning = (
        "Cannot close from existing live RO API surface or Phase63 PARTIAL user report. "
        "Does not require a trade fill. Authoritative broker/session documentation "
        "(or a future permitted session-schedule API) could close this without a genuine fill. "
        "Until such evidence is ingested and verified, programmatic status remains UNKNOWN "
        "and conservative execution block remains required."
    )

    out = {
        "dimension": "sessions",
        "current_state": UNKNOWN,
        "live_api": live_api,
        "phase63_user_reported": phase63,
        "external_documentation": external,
        "inferred_from_gaps": False,
        "rollover_clock": UNKNOWN,
        "holiday_exceptions": UNKNOWN,
        "server_timezone": UNKNOWN,
        "dst_behavior": UNKNOWN,
        "conservative_execution_block_required": True,
        "classification": classification,
        "reasoning": reasoning,
        "can_close_without_fill": True,
        "next_evidence": (
            "Ingest dated authoritative Exness/XAUUSDm session schedule (timezone+DST) "
            "with applicability review, OR gain a permitted MT5 session-schedule API"
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
