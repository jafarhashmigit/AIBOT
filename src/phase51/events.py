"""Non-overlapping events on Phase51 data using Phase49 feature/outcome math (read-only reuse)."""

from __future__ import annotations

from typing import Any

from phase49.constants import EVENT_STRIDE, HORIZON_BARS
from phase49.features import compute_features
from phase49.outcomes import build_outcome
from phase51.data import load_h1, load_m5, load_ticks, ticks_by_m5_bar


def build_day_events(day: str) -> dict[str, Any]:
    m5 = load_m5(day)
    h1 = load_h1(day)
    by_bar = ticks_by_m5_bar(load_ticks(day))
    events = []
    excluded = []
    first, last = 48, len(m5) - (1 + HORIZON_BARS)
    if last < first:
        return {"day": day, "events": [], "excluded": [{"reason": "insufficient_bars"}], "overlap_violations": 0}
    idx = first
    optional = {
        "C04_range_vs_prior",
        "F01_m15_ret",
        "F02_h1_ret",
        "F03_h1_range_pos",
        "F04_mtf_agree",
        "F05_h1_stability",
    }
    while idx <= last:
        buy = build_outcome(action="BUY", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by_bar)
        sell = build_outcome(action="SELL", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by_bar)
        if buy.get("data_quality_status") != "OK" or sell.get("data_quality_status") != "OK":
            excluded.append({"decision_idx": idx, "reason": "bad_outcome"})
            idx += EVENT_STRIDE
            continue
        feats = compute_features(m5=m5, idx=idx, h1=h1, ticks_by_bar=by_bar, prior_day_range=None)
        missing = [k for k, v in feats.items() if v is None and k not in optional]
        if missing:
            excluded.append({"decision_idx": idx, "reason": "missing_features", "missing": missing[:6]})
            idx += EVENT_STRIDE
            continue
        events.append(
            {
                "day": day,
                "decision_bar": str(m5[idx]["timestamp_utc"]),
                "decision_idx": idx,
                "features": feats,
                "buy": buy,
                "sell": sell,
            }
        )
        idx += EVENT_STRIDE
    violations = 0
    for a, b in zip(events, events[1:]):
        if b["decision_idx"] < a["decision_idx"] + HORIZON_BARS:
            violations += 1
    return {"day": day, "events": events, "excluded": excluded, "n_events": len(events), "overlap_violations": violations}


def build_events_for_dates(dates: list[str]) -> dict[str, Any]:
    all_events = []
    by_day = {}
    violations = 0
    excluded_n = 0
    for d in dates:
        rec = build_day_events(d)
        all_events.extend(rec["events"])
        violations += rec["overlap_violations"]
        excluded_n += len(rec.get("excluded") or [])
        by_day[d] = {"n_events": rec.get("n_events", 0), "n_excluded": len(rec.get("excluded") or [])}
    return {
        "dates": dates,
        "n_dates": len(dates),
        "n_events": len(all_events),
        "n_excluded": excluded_n,
        "overlap_violations": violations,
        "by_day": by_day,
        "events": all_events,
    }
