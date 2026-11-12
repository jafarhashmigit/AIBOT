"""Bounded MT5 historical fetch helpers (read-only)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc


def _epoch_utc(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=UTC).strftime("%Y-%m-%d %H:%M:%S")


def fetch_m5_day(handle: Any, symbol: str, day: str, *, wall_deadline: float) -> dict[str, Any]:
    if time.monotonic() > wall_deadline:
        return {"ok": False, "error": "wall_budget", "bars": [], "n": 0, "elapsed_s": 0.0}
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    # clip to research cutoff
    cutoff = datetime(2026, 9, 29, 18, 50, tzinfo=UTC)
    if end > cutoff:
        end = cutoff
    t0 = time.perf_counter()
    rates = handle.copy_rates_range(symbol, handle.TIMEFRAME_M5, start, end)
    elapsed = time.perf_counter() - t0
    if rates is None:
        return {
            "ok": False,
            "error": f"copy_rates_range: {handle.last_error()}",
            "bars": [],
            "n": 0,
            "elapsed_s": elapsed,
            "requested_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "requested_end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "mt5_error": handle.last_error(),
        }
    bars = []
    for row in rates:
        bars.append(
            {
                "time_epoch": int(row["time"]),
                "timestamp_utc": _epoch_utc(int(row["time"])),
                "time_utc": _epoch_utc(int(row["time"])),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": float(row["tick_volume"]),
                "spread": float(row["spread"]) if "spread" in rates.dtype.names else None,
                "real_volume": float(row["real_volume"]) if "real_volume" in rates.dtype.names else None,
            }
        )
    return {
        "ok": True,
        "bars": bars,
        "n": len(bars),
        "elapsed_s": elapsed,
        "requested_start": start.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_end": end.strftime("%Y-%m-%d %H:%M:%S"),
        "actual_start": bars[0]["timestamp_utc"] if bars else None,
        "actual_end": bars[-1]["timestamp_utc"] if bars else None,
        "mt5_error": handle.last_error(),
    }


def fetch_ticks_window(
    handle: Any,
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    wall_deadline: float,
) -> dict[str, Any]:
    if time.monotonic() > wall_deadline:
        return {"ok": False, "error": "wall_budget", "ticks": [], "n": 0, "elapsed_s": 0.0}
    t0 = time.perf_counter()
    ticks = handle.copy_ticks_range(symbol, start, end, handle.COPY_TICKS_ALL)
    elapsed = time.perf_counter() - t0
    if ticks is None:
        return {
            "ok": False,
            "error": f"copy_ticks_range: {handle.last_error()}",
            "ticks": [],
            "n": 0,
            "elapsed_s": elapsed,
            "requested_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "requested_end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "mt5_error": handle.last_error(),
        }
    rows = []
    names = set(ticks.dtype.names or ())
    for row in ticks:
        msc = int(row["time_msc"]) if "time_msc" in names else int(row["time"]) * 1000
        bid = float(row["bid"]) if "bid" in names else None
        ask = float(row["ask"]) if "ask" in names else None
        rows.append(
            {
                "time_epoch": int(row["time"]) if "time" in names else None,
                "time_msc": msc,
                "timestamp_msc": msc,
                "timestamp_utc": datetime.fromtimestamp(msc / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "bid": bid,
                "ask": ask,
                "last": float(row["last"]) if "last" in names else None,
                "volume": float(row["volume"]) if "volume" in names else None,
                "volume_real": float(row["volume_real"]) if "volume_real" in names else None,
                "flags": int(row["flags"]) if "flags" in names else None,
                "spread": (ask - bid) if bid is not None and ask is not None else None,
            }
        )
    return {
        "ok": True,
        "ticks": rows,
        "n": len(rows),
        "elapsed_s": elapsed,
        "requested_start": start.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_end": end.strftime("%Y-%m-%d %H:%M:%S"),
        "actual_start": rows[0]["timestamp_utc"] if rows else None,
        "actual_end": rows[-1]["timestamp_utc"] if rows else None,
        "mt5_error": handle.last_error(),
    }
