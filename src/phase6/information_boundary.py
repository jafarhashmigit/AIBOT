"""Explicit decision-time information boundary.

A payload is allowed at time t only if every field is knowable at t.
Outcome / future fields are rejected here, not at the caller’s discretion.
"""

from __future__ import annotations

from datetime import datetime

from phase6.constants import RESEARCH_CUTOFF

FORBIDDEN_DECISION_TIME_KEYS = frozenset({
    "realized_outcome",
    "realized_r",
    "realized_R",
    "realized_net_r",
    "net_r",
    "net_pnl",
    "actual_net_r",
    "actual_net_pnl",
    "actual_exit_reason",
    "exit_reason",
    "exit_timestamp",
    "exit_time",
    "outcome",
    "outcome_buy_net_r",
    "outcome_sell_net_r",
    "hypothetical_buy_net_r",
    "hypothetical_sell_net_r",
    "selected_action_net_r",
    "future_return",
    "future_price",
    "future_label",
    "future_volume",
    "future_volatility",
    "future_session_outcome",
    "label",
    "target",
    "y",
    "y_true",
})

FORBIDDEN_KEY_PREFIXES = ("future_", "outcome_", "realized_", "actual_")


class InformationBoundaryError(ValueError):
    """Raised when a decision-time object contains forbidden future information."""


def _walk_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, key, value
            yield from _walk_keys(value, path)
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            yield from _walk_keys(value, f"{prefix}[{i}]")


def is_forbidden_key(key: str) -> bool:
    if key in FORBIDDEN_DECISION_TIME_KEYS:
        return True
    return any(key.startswith(p) for p in FORBIDDEN_KEY_PREFIXES)


def assert_decision_time_payload(payload: dict, *, as_of: str | None = None) -> None:
    """Reject future/outcome fields. Optionally reject timestamps after as_of or cutoff."""
    if not isinstance(payload, dict):
        raise InformationBoundaryError("decision-time payload must be a dict")
    bad = []
    for path, key, _value in _walk_keys(payload):
        if is_forbidden_key(str(key)):
            bad.append(path)
    if bad:
        raise InformationBoundaryError(
            "forbidden future/outcome fields at decision time: " + ", ".join(sorted(bad))
        )
    if as_of is not None:
        stamp = payload.get("timestamp") or payload.get("available_history_end")
        if stamp is not None and str(stamp) > as_of:
            raise InformationBoundaryError(
                f"payload timestamp {stamp} is after as_of {as_of}"
            )
        if str(as_of) > RESEARCH_CUTOFF:
            raise InformationBoundaryError(
                f"as_of {as_of} exceeds research cutoff {RESEARCH_CUTOFF}"
            )


def assert_before_cutoff(timestamp: str) -> None:
    if str(timestamp) > RESEARCH_CUTOFF:
        raise InformationBoundaryError(
            f"timestamp {timestamp} exceeds research cutoff {RESEARCH_CUTOFF}"
        )


def assert_strictly_before(timestamp: str, cutoff: str, *, what: str = "timestamp") -> None:
    if str(timestamp) >= str(cutoff):
        raise InformationBoundaryError(f"{what} {timestamp} is not strictly before {cutoff}")


def parse_stamp(value: str) -> datetime:
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
