"""Per-date quality diagnostics — no strategy/outcome analysis."""

from __future__ import annotations

import math
from typing import Any

from phase43.constants import H1_WARMUP_BARS, RAW_H1, RAW_M5, RAW_TICKS, SYMBOL, TICK_HOURS
from phase43.storage import load_jsonl


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f, c = int(math.floor(k)), int(math.ceil(k))
    if f == c:
        return s[f]
    return s[f] * (c - k) + s[c] * (k - f)


def assess_day(day: str) -> dict[str, Any]:
    m5 = load_jsonl(RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl")
    h1 = load_jsonl(RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl")
    hours_empty = []
    hours_nonempty = []
    hours_missing_file = []
    ticks_all = []
    duplicates = 0
    for h in TICK_HOURS:
        path = RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"
        if not path.is_file():
            hours_missing_file.append(h)
            continue
        rows = load_jsonl(path)
        if not rows:
            hours_empty.append(h)
        else:
            hours_nonempty.append(h)
            seen = set()
            for t in rows:
                key = (t.get("timestamp_msc"), t.get("bid"), t.get("ask"))
                if key in seen:
                    duplicates += 1
                seen.add(key)
            ticks_all.extend(rows)

    # M5 gaps
    epochs = [int(b["time_epoch"]) for b in m5]
    unexpected_gaps = 0
    for i in range(1, len(epochs)):
        d = epochs[i] - epochs[i - 1]
        if d != 300 and 0 < d < 1800:
            unexpected_gaps += 1

    spreads = []
    bid_ask_bad = 0
    for t in ticks_all:
        if t.get("bid") is None or t.get("ask") is None:
            bid_ask_bad += 1
            continue
        bid, ask = float(t["bid"]), float(t["ask"])
        if ask < bid or bid <= 0:
            bid_ask_bad += 1
        else:
            spreads.append(ask - bid)

    warmup = [b for b in h1 if (b.get("close_time_utc") or "") < f"{day} 00:00:00"]
    ema20_ready = len(warmup) >= 20
    warmup_30 = len(warmup) >= H1_WARMUP_BARS

    # Session completeness: all 24 hour files present (empty allowed)
    if hours_missing_file:
        session_status = "INCOMPLETE_ACQUISITION"
    elif hours_nonempty:
        session_status = "VERIFIED_COMPLETE_SESSION" if len(hours_missing_file) == 0 and len(hours_nonempty) + len(hours_empty) == 24 else "VERIFIED_PARTIAL_SESSION"
        if len(hours_nonempty) + len(hours_empty) == 24:
            session_status = "VERIFIED_COMPLETE_SESSION"
        else:
            session_status = "VERIFIED_PARTIAL_SESSION"
    else:
        session_status = "EMPTY_OR_FAILED"

    return {
        "day": day,
        "m5_n": len(m5),
        "m5_first": m5[0]["timestamp_utc"] if m5 else None,
        "m5_last": m5[-1]["timestamp_utc"] if m5 else None,
        "m5_unexpected_gaps": unexpected_gaps,
        "h1_n": len(h1),
        "h1_warmup_before_day": len(warmup),
        "h1_warmup_sufficient_30": warmup_30,
        "ema20_ready": ema20_ready,
        "tick_n": len(ticks_all),
        "tick_first": ticks_all[0]["timestamp_utc"] if ticks_all else None,
        "tick_last": ticks_all[-1]["timestamp_utc"] if ticks_all else None,
        "hours_empty": hours_empty,
        "hours_nonempty": hours_nonempty,
        "hours_missing_file": hours_missing_file,
        "duplicate_tick_keys": duplicates,
        "bid_ask_bad": bid_ask_bad,
        "spread_median": _pct(spreads, 50),
        "spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
        "spread_p95": _pct(spreads, 95),
        "spread_p99": _pct(spreads, 99),
        "session_status": session_status,
        "pkt_display_note": "Internal UTC only; PKT = UTC+5 for display if needed",
    }


def assess_all(days: list[str]) -> dict[str, Any]:
    rows = [assess_day(d) for d in days]
    return {
        "n_dates": len(rows),
        "n_complete_sessions": sum(1 for r in rows if r["session_status"] == "VERIFIED_COMPLETE_SESSION"),
        "n_h1_warmup_ok": sum(1 for r in rows if r["h1_warmup_sufficient_30"]),
        "n_ema20_ready": sum(1 for r in rows if r["ema20_ready"]),
        "total_ticks": sum(r["tick_n"] for r in rows),
        "rows": rows,
    }
