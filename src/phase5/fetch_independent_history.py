"""Fetch independent M5 bars from the existing MT5 terminal into a separate file.

Does not append to xauusd_m5.csv. Does not request bars at/after approved start
or after the research cutoff. Does not send orders.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone

import numpy as np

from phase5.constants import (
    APPROVED_M5_START,
    INDEPENDENT_RAW,
    MT5_TERMINAL,
    RESEARCH_CUTOFF,
    SYMBOL,
    TIME_FORMAT,
)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def fetch() -> dict:
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        return {"status": "unavailable", "reason": f"MetaTrader5 import failed: {exc}"}

    approved_start = datetime.strptime(APPROVED_M5_START, TIME_FORMAT)
    cutoff = datetime.strptime(RESEARCH_CUTOFF, TIME_FORMAT)
    probe_end = approved_start - timedelta(minutes=5)

    if not mt5.initialize(path=MT5_TERMINAL, timeout=60000):
        err = mt5.last_error()
        return {"status": "unavailable", "reason": f"MT5 initialize failed: {err}"}

    rows = []
    try:
        if not mt5.symbol_select(SYMBOL, True):
            return {"status": "unavailable", "reason": f"{SYMBOL} not available: {mt5.last_error()}"}
        year, month = 2025, 6
        while (year, month) <= (2026, 2):
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            last_day = monthrange(year, month)[1]
            end = datetime(year, month, last_day, 23, 59, tzinfo=timezone.utc)
            if end >= approved_start.replace(tzinfo=timezone.utc):
                end = probe_end.replace(tzinfo=timezone.utc)
            rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, start, end)
            n = 0 if rates is None else len(rates)
            if n:
                for rec in rates:
                    stamp = datetime.utcfromtimestamp(int(rec["time"]))
                    if stamp >= approved_start or stamp.strftime(TIME_FORMAT) >= RESEARCH_CUTOFF:
                        continue
                    rows.append({
                        "time": stamp.strftime(TIME_FORMAT),
                        "open": float(rec["open"]),
                        "high": float(rec["high"]),
                        "low": float(rec["low"]),
                        "close": float(rec["close"]),
                        "tick_volume": int(rec["tick_volume"]),
                        "spread": float(rec["spread"]),
                    })
            month += 1
            if month == 13:
                year, month = year + 1, 1
    finally:
        mt5.shutdown()

    if not rows:
        return {"status": "unavailable", "reason": "MT5 returned no independent bars", "n": 0}

    # Deduplicate by time, keep first, chronological.
    seen = set()
    unique = []
    for rec in sorted(rows, key=lambda r: r["time"]):
        if rec["time"] in seen:
            continue
        seen.add(rec["time"])
        unique.append(rec)
    if unique[-1]["time"] >= APPROVED_M5_START or unique[-1]["time"] >= RESEARCH_CUTOFF:
        return {"status": "unavailable", "reason": "fetch produced a bar at/after the approved start or cutoff"}

    INDEPENDENT_RAW.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(INDEPENDENT_RAW, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["time", "open", "high", "low", "close", "tick_volume", "spread"])
        w.writeheader()
        w.writerows(unique)
    return {
        "status": "ok",
        "path": str(INDEPENDENT_RAW),
        "n": len(unique),
        "first": unique[0]["time"],
        "last": unique[-1]["time"],
        "approved_m5_start": APPROVED_M5_START,
        "cutoff": RESEARCH_CUTOFF,
        "appended_to_xauusd_m5": False,
    }
