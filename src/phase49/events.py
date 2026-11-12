"""Non-overlapping H12 event construction."""

from __future__ import annotations

from typing import Any

from phase49.constants import EVENT_STRIDE, HORIZON_BARS
from phase49.data import load_h1, load_m5, load_ticks, ticks_by_m5_bar
from phase49.features import compute_features
from phase49.outcomes import build_outcome


def prior_day_range_from_m5(m5: list[dict[str, Any]], day: str) -> float | None:
    """If prior calendar day bars appear in file (rare), else None — use first-session proxy later."""
    # Phase49 m5 files are single-day; prior day range unknown without extra download.
    # Use None → C04 missing → excluded from hypotheses needing C04.
    return None


def build_day_events(day: str) -> dict[str, Any]:
    m5 = load_m5(day)
    h1 = load_h1(day)
    ticks = load_ticks(day)
    by_bar = ticks_by_m5_bar(ticks)
    prior_range = prior_day_range_from_m5(m5, day)

    excluded: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    # First decision idx needs feature lookback 48 and ATR; last needs entry+horizon
    first = 48
    last = len(m5) - (1 + HORIZON_BARS)
    if last < first:
        return {
            "day": day,
            "events": [],
            "excluded": [{"reason": "insufficient_bars", "m5_n": len(m5)}],
            "overlap_violations": 0,
        }

    idx = first
    prev_exit_idx = -10**9
    while idx <= last:
        # enforce non-overlap: next decision entry must be >= previous exit+1
        # decision at idx → entry idx+1 → exit idx+HORIZON → next decision >= exit
        if idx + 1 <= prev_exit_idx:
            idx += 1
            continue

        buy = build_outcome(action="BUY", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by_bar)
        sell = build_outcome(action="SELL", day=day, decision_idx=idx, m5=m5, ticks_by_bar=by_bar)
        if buy.get("data_quality_status") != "OK" or sell.get("data_quality_status") != "OK":
            excluded.append(
                {
                    "decision_bar": str(m5[idx]["timestamp_utc"]),
                    "reason": "invalid_buy_or_sell_outcome",
                    "buy": buy.get("data_quality_status"),
                    "sell": sell.get("data_quality_status"),
                }
            )
            idx += EVENT_STRIDE
            continue

        feats = compute_features(
            m5=m5, idx=idx, h1=h1, ticks_by_bar=by_bar, prior_day_range=prior_range
        )
        # Core required families A/B/C*/D/E; C04 and F_* may be missing without dropping the event
        optional = {
            "C04_range_vs_prior",
            "F01_m15_ret",
            "F02_h1_ret",
            "F03_h1_range_pos",
            "F04_mtf_agree",
            "F05_h1_stability",
        }
        missing = [k for k, v in feats.items() if v is None and k not in optional]
        if missing:
            excluded.append(
                {
                    "decision_bar": str(m5[idx]["timestamp_utc"]),
                    "reason": "missing_features",
                    "missing": missing[:8],
                }
            )
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
        prev_exit_idx = idx + HORIZON_BARS  # exit idx = entry+H-1 = idx+H; next decision >= exit
        # stride: jump by EVENT_STRIDE (=12) ensures non-overlap when start spaced by 12
        idx += EVENT_STRIDE

    # overlap verification
    violations = 0
    for a, b in zip(events, events[1:]):
        # exit of a is decision_idx + HORIZON; next decision must be >= that
        if b["decision_idx"] < a["decision_idx"] + HORIZON_BARS:
            violations += 1

    return {
        "day": day,
        "events": events,
        "excluded": excluded,
        "n_events": len(events),
        "n_excluded": len(excluded),
        "overlap_violations": violations,
        "m5_n": len(m5),
        "tick_n": len(ticks),
    }


def build_events_for_dates(dates: list[str]) -> dict[str, Any]:
    by_day = {}
    all_events = []
    excluded_total = 0
    violations = 0
    for d in dates:
        rec = build_day_events(d)
        by_day[d] = {
            "n_events": rec["n_events"],
            "n_excluded": rec["n_excluded"],
            "overlap_violations": rec["overlap_violations"],
            "excluded_sample": rec["excluded"][:5],
            "m5_n": rec["m5_n"],
            "tick_n": rec["tick_n"],
        }
        all_events.extend(rec["events"])
        excluded_total += rec["n_excluded"]
        violations += rec["overlap_violations"]
    return {
        "dates": dates,
        "n_dates": len(dates),
        "n_events": len(all_events),
        "n_excluded": excluded_total,
        "overlap_violations": violations,
        "events_per_date": {d: by_day[d]["n_events"] for d in dates},
        "by_day": by_day,
        "events": all_events,
    }
