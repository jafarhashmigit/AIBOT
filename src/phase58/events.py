"""Non-overlapping H12 events with Phase58 features + Phase49 outcomes."""

from __future__ import annotations

from typing import Any

from phase49.outcomes import build_outcome
from phase58.constants import EVENT_STRIDE, HORIZON_BARS
from phase58.data import (
    list_all_days,
    load_m5_raw,
    load_ticks,
    previous_archived_day,
    ticks_by_m5_bar,
)
from phase58.features import compute_phase58_features


def build_day_events(day: str) -> dict[str, Any]:
    m5 = load_m5_raw(day)
    ticks = load_ticks(day)
    by_bar = ticks_by_m5_bar(ticks)
    all_days = list_all_days()
    prev = previous_archived_day(day, all_days)
    prior_m5 = None
    if prev:
        try:
            prior_m5 = load_m5_raw(prev, allow_sealed_context=True)
        except Exception:
            prior_m5 = None

    events: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    first = 48
    last = len(m5) - (1 + HORIZON_BARS)
    if last < first:
        return {"day": day, "events": [], "excluded": [{"reason": "insufficient_bars"}], "overlap_violations": 0}

    idx = first
    prev_exit_idx = -10**9
    while idx <= last:
        if idx + 1 <= prev_exit_idx:
            idx += 1
            continue
        buy = build_outcome(action="BUY", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by_bar)
        sell = build_outcome(action="SELL", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by_bar)
        if buy.get("data_quality_status") != "OK" or sell.get("data_quality_status") != "OK":
            excluded.append({"idx": idx, "reason": "bad_outcome"})
            idx += EVENT_STRIDE
            continue
        feats = compute_phase58_features(m5=m5, idx=idx, ticks_by_bar=by_bar, prior_session_m5=prior_m5)
        exit_idx = idx + HORIZON_BARS
        events.append(
            {
                "day": day,
                "decision_idx": idx,
                "decision_bar": str(m5[idx]["timestamp_utc"]),
                "features": feats,
                "buy": buy,
                "sell": sell,
                "prior_session_day": prev,
            }
        )
        prev_exit_idx = exit_idx
        idx += EVENT_STRIDE

    return {"day": day, "events": events, "excluded": excluded, "overlap_violations": 0}


def build_events_for_days(days: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in days:
        out.extend(build_day_events(d)["events"])
    return out
