"""Per-date alignment of M5 / H1 / ticks and H12 path coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from phase40.constants import HORIZON_BARS, RAW_H1, RAW_M5, RAW_TICKS, SYMBOL, TARGET_DATES, TICK_HOURS
from phase40.storage import load_jsonl, m5_done, h1_done, tick_hour_done
from phase40.validation import classify_session

UTC = timezone.utc


def _ticks_by_bar(day: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for h in TICK_HOURS:
        if not tick_hour_done(day, h):
            continue
        for t in load_jsonl(RAW_TICKS / f"ticks_{SYMBOL}_{day}_{h:02d}h.jsonl"):
            ts = t["timestamp_utc"]
            minute = int(ts[14:16])
            floored = minute - (minute % 5)
            bar = f"{ts[:14]}{floored:02d}:00"
            out.setdefault(bar, []).append(t)
    return out


def align_day(day: str) -> dict[str, Any]:
    m5 = load_jsonl(RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl") if m5_done(day) else []
    h1 = load_jsonl(RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl") if h1_done(day) else []
    session = classify_session(day)
    ticks_by_bar = _ticks_by_bar(day)

    eval_start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    warmup = [b for b in h1 if b.get("close_time_utc", "") <= eval_start.strftime("%Y-%m-%d %H:%M:%S")]
    # EMA20 warm-up: need >=20 completed H1 before a decision; report how many available before day
    ema20_ready_at = None
    if len(warmup) >= 20:
        ema20_ready_at = warmup[19].get("close_time_utc")

    times = [b["timestamp_utc"] for b in m5]
    h12_eligible = 0
    h12_ineligible = 0
    for i, t in enumerate(times):
        last = i + HORIZON_BARS  # entry at i+1 through i+12 => need indices i+1..i+12
        if i + 1 + HORIZON_BARS - 1 >= len(times):
            continue
        horizon = times[i + 1 : i + 1 + HORIZON_BARS]
        if all(bt in ticks_by_bar and ticks_by_bar[bt] for bt in horizon):
            h12_eligible += 1
        else:
            h12_ineligible += 1

    return {
        "day": day,
        "m5_n": len(m5),
        "m5_first": times[0] if times else None,
        "m5_last": times[-1] if times else None,
        "h1_n": len(h1),
        "h1_warmup_n": len(warmup),
        "h1_warmup_sufficient_30": len(warmup) >= 30,
        "ema20_warmup_ready": len(warmup) >= 20,
        "ema20_ready_at_utc": ema20_ready_at,
        "tick_session": session,
        "n_m5_bars_with_ticks": sum(1 for t in times if ticks_by_bar.get(t)),
        "h12_path_eligible_signal_slots": h12_eligible,
        "h12_path_ineligible_signal_slots": h12_ineligible,
        "flags": {
            "missing_m5": not bool(m5),
            "missing_h1": not bool(h1),
            "partial_ticks": session.get("status") == "VERIFIED_PARTIAL_SESSION",
            "complete_session_ticks": session.get("status") == "VERIFIED_COMPLETE_SESSION",
        },
    }


def align_all() -> dict[str, Any]:
    rows = [align_day(d) for d in TARGET_DATES]
    return {
        "dates": rows,
        "n_complete_tick_sessions": sum(1 for r in rows if r["flags"]["complete_session_ticks"]),
        "n_partial_tick_sessions": sum(1 for r in rows if r["flags"]["partial_ticks"]),
        "n_h1_warmup_ok": sum(1 for r in rows if r["h1_warmup_sufficient_30"]),
        "n_ema20_ready": sum(1 for r in rows if r["ema20_warmup_ready"]),
    }
