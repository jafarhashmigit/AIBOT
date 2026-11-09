"""Attach market-path outcomes after 12 completed M5 bars. Not a trade P&L."""

from __future__ import annotations

from phase12.timestamp_normalizer import add_minutes_utc
from phase12.validation import HORIZON_BARS, HORIZON_MINUTES, SOURCE_FORWARD, ShadowError


def is_visible(outcome_end: str, as_of: str) -> bool:
    return outcome_end < as_of


def observe_outcome(
    decision: dict,
    subsequent_bars: list[dict],
    *,
    as_of_utc: str,
) -> dict:
    start = decision["decision_timestamp_utc"]
    planned_end = add_minutes_utc(start, HORIZON_MINUTES)
    status = {
        "decision_id": decision["decision_id"],
        "source_type": SOURCE_FORWARD,
        "outcome_start_timestamp": start,
        "outcome_end_timestamp": planned_end,
        "observed_future_bars": 0,
        "future_high": "",
        "future_low": "",
        "future_close": "",
        "outcome_completeness": "pending",
        "gap_detected": False,
        "outcome_status": "pending",
        "hypothetical_counterfactual": "",
        "note": "market-path observation only; not paper P&L; not an agent trade",
    }
    if not is_visible(planned_end, as_of_utc):
        return status
    if planned_end == as_of_utc:
        return status

    path = []
    prev_open = None
    for bar in subsequent_bars:
        if bar["bar_open_timestamp_utc"] < start:
            continue
        if bar["bar_open_timestamp_utc"] >= planned_end:
            continue
        if prev_open is not None:
            from phase12.bar_validator import gap_status
            if gap_status(prev_open, bar["bar_open_timestamp_utc"]) == "gap":
                status["gap_detected"] = True
                status["outcome_completeness"] = "excluded_gap"
                status["outcome_status"] = "excluded_gap"
                return status
        path.append(bar)
        prev_open = bar["bar_open_timestamp_utc"]
        if len(path) >= HORIZON_BARS:
            break

    status["observed_future_bars"] = len(path)
    if len(path) < HORIZON_BARS:
        status["outcome_completeness"] = "incomplete"
        status["outcome_status"] = "pending"
        return status
    if not is_visible(planned_end, as_of_utc):
        status["outcome_status"] = "pending"
        return status
    highs = [float(b["high"]) for b in path]
    lows = [float(b["low"]) for b in path]
    status["future_high"] = max(highs)
    status["future_low"] = min(lows)
    status["future_close"] = float(path[-1]["close"])
    status["outcome_completeness"] = "complete"
    status["outcome_status"] = "complete"
    return status
