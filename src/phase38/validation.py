"""Data-quality validation — never silently repair."""

from __future__ import annotations

import math
from typing import Any

M5_SECONDS = 300


def _finite(x: Any) -> bool:
    try:
        v = float(x)
        return math.isfinite(v)
    except (TypeError, ValueError):
        return False


def validate_m5_bars(bars: list[dict[str, Any]]) -> dict[str, Any]:
    rejected: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for i, b in enumerate(bars):
        reasons = []
        for k in ("open", "high", "low", "close"):
            if not _finite(b.get(k)) or float(b[k]) <= 0:
                reasons.append(f"bad_{k}")
        o, h, l, c = (float(b.get(k) or 0) for k in ("open", "high", "low", "close"))
        if not reasons:
            if not (h >= max(o, c) and l <= min(o, c) and h >= l):
                reasons.append("invalid_ohlc")
        if b.get("timestamp_utc") is None and b.get("time_utc") is None:
            reasons.append("missing_timestamp")
        if reasons:
            rejected.append({"index": i, "reasons": reasons, "record": b})
        else:
            accepted.append(b)

    times = []
    for b in accepted:
        te = b.get("time_epoch")
        if te is not None:
            times.append(int(te))
    dup = len(times) - len(set(times)) if times else 0
    ooo = sum(1 for i in range(1, len(times)) if times[i] < times[i - 1])
    gaps = []
    unexpected = 0
    session = 0
    for i in range(1, len(times)):
        d = times[i] - times[i - 1]
        if d == M5_SECONDS:
            continue
        if d <= 0:
            continue
        gaps.append(d)
        if d >= 30 * 60:
            session += 1
        else:
            unexpected += 1

    return {
        "n_input": len(bars),
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "duplicate_timestamps": dup,
        "out_of_order": ooo,
        "missing_intervals": len(gaps),
        "unexpected_gaps_lt_30m": unexpected,
        "session_gaps_ge_30m": session,
        "largest_gap_seconds": max(gaps) if gaps else 0,
        "pass": len(rejected) == 0 and ooo == 0,
        "rejected": rejected[:50],  # cap for report size
        "accepted": accepted,
    }


def validate_ticks(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    rejected: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for i, t in enumerate(ticks):
        reasons = []
        bid, ask = t.get("bid"), t.get("ask")
        if bid is None or ask is None:
            reasons.append("missing_bid_ask")
        elif not _finite(bid) or not _finite(ask) or float(bid) <= 0 or float(ask) <= 0:
            reasons.append("nonpositive_or_nonfinite_bid_ask")
        else:
            if float(bid) > float(ask):
                reasons.append("crossed_market")
            if float(ask) - float(bid) < 0:
                reasons.append("negative_spread")
            if float(ask) - float(bid) == 0:
                reasons.append("zero_spread")
        if t.get("timestamp_msc") is None and t.get("time_msc") is None:
            reasons.append("missing_timestamp_msc")
        if reasons:
            rejected.append({"index": i, "reasons": reasons, "record": t})
        else:
            accepted.append(t)

    mscs = [int(t.get("timestamp_msc") or t.get("time_msc")) for t in accepted]
    dup = len(mscs) - len(set(mscs)) if mscs else 0
    ooo = sum(1 for i in range(1, len(mscs)) if mscs[i] < mscs[i - 1])
    stale_repeats = sum(1 for i in range(1, len(mscs)) if mscs[i] == mscs[i - 1])

    return {
        "n_input": len(ticks),
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "duplicate_timestamps_msc": dup,
        "out_of_order": ooo,
        "stale_or_repeated_timestamps": stale_repeats,
        "pass": len(rejected) == 0 and ooo == 0,
        "rejected": rejected[:50],
        "accepted": accepted,
    }


def classify_interval(requested_n_expected: int | None, n_returned: int, first: str | None, last: str | None, error: str | None) -> str:
    if error:
        return "UNAVAILABLE_OR_FAILED"
    if n_returned <= 0:
        return "EMPTY_INTERVAL"
    # For probes we often don't know exact expected count; partial if ends don't cover request tightly
    if requested_n_expected is not None and n_returned < requested_n_expected:
        return "VERIFIED_PARTIAL_INTERVAL"
    if first and last:
        return "VERIFIED_COMPLETE_INTERVAL" if requested_n_expected is None else (
            "VERIFIED_COMPLETE_INTERVAL" if n_returned >= requested_n_expected else "VERIFIED_PARTIAL_INTERVAL"
        )
    return "VERIFIED_PARTIAL_INTERVAL"
