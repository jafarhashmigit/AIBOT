"""Source-type, temporal, and integrity guards. Fail closed."""

from __future__ import annotations

from phase3.nplib import sha256_file
from phase6.information_boundary import InformationBoundaryError, is_forbidden_key
from phase8.experience_schema import outcome_end_for
from phase10.constants import (
    ALLOWED_SOURCES,
    MAX_ACCESS_TIMESTAMP,
    OUTCOME_KEYS,
    PROJECT_ROOT,
    PROTECTED_HASHES,
    RESEARCH_CUTOFF,
    SOURCE_HISTORICAL,
    SOURCE_PAPER,
)


class Phase10Error(ValueError):
    pass


class SourceSeparationError(Phase10Error):
    pass


class TemporalSafetyError(Phase10Error):
    pass


class IntegrityError(RuntimeError):
    pass


def require_source(source_type: str, expected: str | None = None) -> str:
    if source_type is None or str(source_type).strip() == "":
        raise SourceSeparationError("missing source type")
    source = str(source_type)
    if source not in ALLOWED_SOURCES:
        raise SourceSeparationError(f"unknown source type: {source}")
    if expected is not None and source != expected:
        raise SourceSeparationError(f"expected {expected}, got {source}")
    return source


def assert_no_outcome_keys(payload: dict) -> None:
    for key in payload:
        if is_forbidden_key(str(key)) or str(key) in OUTCOME_KEYS:
            raise InformationBoundaryError(f"outcome key in decision-time payload: {key}")


def assert_timestamp_allowed(stamp: str, *, what: str = "timestamp") -> None:
    if str(stamp) > RESEARCH_CUTOFF:
        raise TemporalSafetyError(f"{what} {stamp} after research cutoff")
    if str(stamp) > MAX_ACCESS_TIMESTAMP:
        raise TemporalSafetyError(f"{what} {stamp} after max access timestamp")


def assert_visible(outcome_end: str, as_of: str) -> None:
    """Strict: outcome_end < as_of. Equality remains unavailable."""
    if not (str(outcome_end) < str(as_of)):
        raise TemporalSafetyError(
            f"experience with outcome_end {outcome_end} is not visible at {as_of}"
        )


def is_visible(outcome_end: str, as_of: str) -> bool:
    return str(outcome_end) < str(as_of)


def assert_complete(outcome_status: str) -> None:
    if outcome_status != "completed":
        raise TemporalSafetyError("incomplete outcome excluded from retrieval")


def snapshot_protected() -> dict:
    out = {}
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        actual = sha256_file(path) if path.exists() else None
        out[rel] = {
            "expected": expected,
            "actual": actual,
            "unchanged": actual == expected,
            "exists": path.exists(),
        }
        if not path.exists():
            raise IntegrityError(f"HARD FAILURE: protected artifact missing: {rel}")
        if actual != expected:
            raise IntegrityError(f"HARD FAILURE: protected artifact changed: {rel}")
    return out


def historical_id(timestamp: str, side: str) -> str:
    return f"hist:{timestamp}:{side}"


def paper_decision_id(timestamp: str) -> str:
    return f"paper:{timestamp}:XAUUSD:M5"


def paper_trade_id(decision_id: str) -> str:
    return f"{decision_id}:trade"


# Re-export horizon helper so Phase 10 does not copy Phase 8 source.
outcome_end_for = outcome_end_for
