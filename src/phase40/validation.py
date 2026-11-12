"""Validation helpers and session classification."""

from __future__ import annotations

import math
from typing import Any

from phase40.constants import SYMBOL, TICK_HOURS
from phase40.storage import load_jsonl, tick_hour_done
from phase40.constants import RAW_TICKS


def _finite_pos(x: Any) -> bool:
    try:
        v = float(x)
        return math.isfinite(v) and v > 0
    except (TypeError, ValueError):
        return False


def validate_m5(bars: list[dict[str, Any]]) -> dict[str, Any]:
    accepted, rejected = [], []
    for i, b in enumerate(bars):
        reasons = []
        for k in ("open", "high", "low", "close"):
            if not _finite_pos(b.get(k)):
                reasons.append(f"bad_{k}")
        if not reasons:
            o, h, l, c = (float(b[k]) for k in ("open", "high", "low", "close"))
            if not (h >= max(o, c) and l <= min(o, c) and h >= l):
                reasons.append("invalid_ohlc")
        if reasons:
            rejected.append({"index": i, "reasons": reasons})
        else:
            accepted.append(b)
    times = [int(b["time_epoch"]) for b in accepted]
    ooo = sum(1 for i in range(1, len(times)) if times[i] < times[i - 1])
    dup = len(times) - len(set(times))
    return {
        "pass": not rejected and ooo == 0,
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "out_of_order": ooo,
        "duplicates": dup,
        "accepted": accepted,
        "rejected": rejected[:20],
    }


def validate_ticks(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    accepted, rejected = [], []
    for i, t in enumerate(ticks):
        reasons = []
        bid, ask = t.get("bid"), t.get("ask")
        if bid is None or ask is None or not _finite_pos(bid) or not _finite_pos(ask):
            reasons.append("bad_bid_ask")
        elif float(bid) > float(ask):
            reasons.append("crossed")
        if t.get("timestamp_msc") is None:
            reasons.append("missing_msc")
        if reasons:
            rejected.append({"index": i, "reasons": reasons})
        else:
            accepted.append(t)
    mscs = [int(t["timestamp_msc"]) for t in accepted]
    ooo = sum(1 for i in range(1, len(mscs)) if mscs[i] < mscs[i - 1])
    return {
        "pass": not rejected and ooo == 0,
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "out_of_order": ooo,
        "duplicates_msc": len(mscs) - len(set(mscs)),
        "accepted": accepted,
        "rejected": rejected[:20],
    }


def classify_session(day: str) -> dict[str, Any]:
    """Classify tick session completeness. Partial ≠ complete."""
    missing_hours = [h for h in TICK_HOURS if not tick_hour_done(day, h)]
    if missing_hours:
        if len(missing_hours) == 24:
            return {
                "status": "NOT_PROBED" if True else "EMPTY_INTERVAL",
                "missing_hours": missing_hours,
                "note": "not all 24 hour chunks present on disk",
            }
        return {
            "status": "VERIFIED_PARTIAL_SESSION",
            "missing_hours": missing_hours,
            "hours_present": 24 - len(missing_hours),
            "note": "Some hour chunks missing/failed — NOT a complete session",
        }

    # all 24 files present — inspect content
    nonempty = 0
    empty = 0
    firsts, lasts = [], []
    total = 0
    for h in TICK_HOURS:
        rows = load_jsonl(RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl")
        total += len(rows)
        if rows:
            nonempty += 1
            firsts.append(rows[0]["timestamp_utc"])
            lasts.append(rows[-1]["timestamp_utc"])
        else:
            empty += 1
    if total == 0:
        return {"status": "EMPTY_INTERVAL", "hours_empty": empty, "n_ticks": 0}
    return {
        "status": "VERIFIED_COMPLETE_SESSION",
        "hours_nonempty": nonempty,
        "hours_empty": empty,
        "n_ticks": total,
        "first_tick": min(firsts) if firsts else None,
        "last_tick": max(lasts) if lasts else None,
        "note": "All 24 UTC hour chunks retrieved (empty hours allowed if source returned empty)",
    }
