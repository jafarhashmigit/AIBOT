"""Evidence freshness and conflict policy."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from phase64_12.constants import (
    DST_WINTER_EFFECTIVE,
    FRESHNESS_POLICY_VERSION,
    MAX_EVIDENCE_AGE_DAYS,
    NEXT_US_DST_START,
    RETRIEVAL_DATE,
    SCHEDULE_VERSION,
    UNKNOWN,
    canonical_json_sha256,
)


def freshness_policy(
    *,
    retrieved_on: str = RETRIEVAL_DATE,
    verified_on: str | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.fromisoformat(RETRIEVAL_DATE)
    retrieved = date.fromisoformat(retrieved_on)
    verified = date.fromisoformat(verified_on or retrieved_on)
    age_days = (as_of - retrieved).days
    winter_start = date.fromisoformat(DST_WINTER_EFFECTIVE)
    summer_start = date.fromisoformat(NEXT_US_DST_START)

    expired = age_days > MAX_EVIDENCE_AGE_DAYS
    # Season validity window for current winter schedule body
    season_valid = winter_start <= as_of < summer_start

    status = "FRESH"
    if expired:
        status = "EXPIRED"
    elif not season_valid:
        status = "OUTSIDE_EFFECTIVE_SEASON_WINDOW"

    out = {
        "policy_version": FRESHNESS_POLICY_VERSION,
        "schedule_version": SCHEDULE_VERSION,
        "source_retrieval_timestamp": f"{retrieved_on}T00:00:00Z",
        "last_verification_timestamp": f"{verified.isoformat()}T00:00:00Z",
        "effective_date": DST_WINTER_EFFECTIVE,
        "effective_until_exclusive": NEXT_US_DST_START,
        "max_age_days": MAX_EVIDENCE_AGE_DAYS,
        "age_days": age_days,
        "status": status,
        "usable": status == "FRESH" and season_valid and not expired,
        "conflict_policy": (
            "If official sources conflict on overlapping weekday segments, preserve both, "
            "raise CONFLICT, and set effective session state UNKNOWN for affected intervals"
        ),
        "continuous_validity_claim": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def evaluate_conflict(
    *,
    source_a_segments: list[dict[str, str]] | None,
    source_b_segments: list[dict[str, str]] | None,
) -> dict[str, Any]:
    """Compare two segment lists for the same weekday; do not silently pick one."""
    if source_a_segments is None or source_b_segments is None:
        return {"conflict": False, "effective_state": None, "note": "incomplete_pair"}
    if source_a_segments == source_b_segments:
        return {"conflict": False, "effective_state": None, "preserved": [source_a_segments]}
    return {
        "conflict": True,
        "effective_state": UNKNOWN,
        "preserved": [source_a_segments, source_b_segments],
        "note": "Both observations preserved; execution state UNKNOWN where conflict affects gating",
    }


def is_evidence_expired(*, retrieved_on: str, as_of_utc: datetime | None = None) -> bool:
    as_of = (as_of_utc or datetime.now(timezone.utc)).date()
    return freshness_policy(retrieved_on=retrieved_on, as_of=as_of)["status"] == "EXPIRED"
