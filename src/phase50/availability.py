"""Causal experience visibility: outcome must be known BEFORE decision time."""

from __future__ import annotations

from typing import Any


def outcome_known_before(outcome_timestamp_utc: str | None, decision_timestamp_utc: str) -> bool:
    if outcome_timestamp_utc is None:
        return False
    # Lexicographic compare works for "YYYY-MM-DD HH:MM:SS[.mmm]" UTC strings
    return str(outcome_timestamp_utc) < str(decision_timestamp_utc)


def experience_available_at(
    records: list[dict[str, Any]],
    decision_timestamp_utc: str,
) -> list[dict[str, Any]]:
    """Return only experiences whose outcomes matured before decision_timestamp."""
    out = []
    for r in records:
        if outcome_known_before(r.get("outcome_timestamp_utc"), decision_timestamp_utc):
            out.append(r)
    return out


def assert_no_leakage(used: list[dict[str, Any]], decision_timestamp_utc: str) -> dict[str, Any]:
    violations = []
    for r in used:
        ot = r.get("outcome_timestamp_utc")
        if not outcome_known_before(ot, decision_timestamp_utc):
            violations.append(
                {
                    "experience_id": r.get("experience_id"),
                    "outcome_timestamp_utc": ot,
                    "decision_timestamp_utc": decision_timestamp_utc,
                }
            )
    return {"ok": len(violations) == 0, "n_violations": len(violations), "sample": violations[:10]}
