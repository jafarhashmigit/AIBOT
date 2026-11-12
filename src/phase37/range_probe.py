"""Bounded historical range probes — no unlimited downloads."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from phase37.bars import fetch_m5_range
from phase37.constants import RANGE_CHECKPOINTS
from phase37.ticks import fetch_ticks_range

UTC = timezone.utc


def probe_history_range(handle: Any, symbol: str, *, wall_deadline: float) -> dict[str, Any]:
    m5_hits: list[dict[str, Any]] = []
    tick_hits: list[dict[str, Any]] = []
    earliest_m5: str | None = None
    earliest_tick: str | None = None

    for cp in RANGE_CHECKPOINTS:
        if time.monotonic() > wall_deadline:
            break
        # Probe liquid hours (12:00–18:00 UTC) to avoid daily gold session breaks at 00:00.
        start = cp.replace(hour=12, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=6)
        m5 = fetch_m5_range(handle, symbol, start, end, wall_deadline=wall_deadline)
        first = (m5.get("analysis") or {}).get("first_timestamp_utc")
        last = (m5.get("analysis") or {}).get("last_timestamp_utc")
        n = int(m5.get("n") or 0)
        # Reject broker "earliest available" bars that fall outside the requested window.
        in_window = False
        if first and last:
            try:
                fdt = datetime.strptime(first, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                ldt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                in_window = fdt >= start - timedelta(hours=1) and ldt <= end + timedelta(hours=1)
            except ValueError:
                in_window = False
        m5_rec = {
            "checkpoint_utc": cp.strftime("%Y-%m-%d"),
            "ok": bool(m5.get("ok")),
            "n": n,
            "first": first,
            "last": last,
            "in_requested_window": in_window,
            "error": m5.get("error"),
            "elapsed_s": m5.get("elapsed_s"),
        }
        m5_hits.append(m5_rec)
        if n > 0 and in_window and first:
            earliest_m5 = first  # checkpoints newest→oldest; overwrite with older confirms

        if time.monotonic() > wall_deadline:
            break
        # 30-minute tick probe in liquid window
        t_end = start + timedelta(minutes=30)
        tk = fetch_ticks_range(handle, symbol, start, t_end, wall_deadline=wall_deadline)
        tk_first = (tk.get("analysis") or {}).get("first_tick_utc")
        tk_n = int(tk.get("n") or 0)
        tk_rec = {
            "checkpoint_utc": cp.strftime("%Y-%m-%d"),
            "ok": bool(tk.get("ok")),
            "n": tk_n,
            "first": tk_first,
            "last": (tk.get("analysis") or {}).get("last_tick_utc"),
            "error": tk.get("error"),
            "elapsed_s": tk.get("elapsed_s"),
        }
        tick_hits.append(tk_rec)
        if tk_n > 0 and tk_first:
            earliest_tick = tk_first

    return {
        "checkpoints": [c.strftime("%Y-%m-%d") for c in RANGE_CHECKPOINTS],
        "m5_probes": m5_hits,
        "tick_probes": tick_hits,
        "EARLIEST_CONFIRMED_M5": earliest_m5,
        "EARLIEST_CONFIRMED_TICK": earliest_tick,
        "note": (
            "Confirmed only when API returned n>0 rows inside the requested liquid-hours window; "
            "empty results and out-of-window 'earliest available' bars do not count."
        ),
    }
