"""Bounded MT5 historical fetches (M5 / H1 / tick hours)."""

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
    t0 = time.perf_counter()
    rates = handle.copy_rates_range(symbol, handle.TIMEFRAME_M5, start, end)
    elapsed = time.perf_counter() - t0
    if rates is None:
        return {
            "ok": False,
            "error": f"copy_rates_range M5: {handle.last_error()}",
            "bars": [],
            "n": 0,
            "elapsed_s": elapsed,
            "requested_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "requested_end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "mt5_error": handle.last_error(),
        }
    bars = [
        {
            "time_epoch": int(r["time"]),
            "timestamp_utc": _epoch_utc(int(r["time"])),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "tick_volume": float(r["tick_volume"]),
            "spread": float(r["spread"]) if "spread" in rates.dtype.names else None,
            "real_volume": float(r["real_volume"]) if "real_volume" in rates.dtype.names else None,
        }
        for r in rates
    ]
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


def fetch_h1_warmup(
    handle: Any,
    symbol: str,
    eval_day: str,
    *,
    warmup_bars: int,
    wall_deadline: float,
) -> dict[str, Any]:
    """Fetch H1 bars ending before eval_day 00:00, plus eval_day H1 (completed only at save time)."""
    if time.monotonic() > wall_deadline:
        return {"ok": False, "error": "wall_budget", "bars": [], "n": 0, "elapsed_s": 0.0}
    eval_start = datetime.strptime(eval_day, "%Y-%m-%d").replace(tzinfo=UTC)
    # Request enough calendar days for ~warmup_bars + eval day (~40 hours buffer)
    start = eval_start - timedelta(days=4)
    end = eval_start + timedelta(days=1) - timedelta(seconds=1)
    t0 = time.perf_counter()
    rates = handle.copy_rates_range(symbol, handle.TIMEFRAME_H1, start, end)
    elapsed = time.perf_counter() - t0
    if rates is None:
        return {
            "ok": False,
            "error": f"copy_rates_range H1: {handle.last_error()}",
            "bars": [],
            "n": 0,
            "elapsed_s": elapsed,
            "requested_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "requested_end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "mt5_error": handle.last_error(),
        }
    bars = []
    for r in rates:
        ot = _epoch_utc(int(r["time"]))
        # open time; completed H1 close = open+1h
        close_t = (datetime.strptime(ot, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) + timedelta(hours=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        bars.append(
            {
                "time_epoch": int(r["time"]),
                "timestamp_utc": ot,
                "close_time_utc": close_t,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "tick_volume": float(r["tick_volume"]),
                "spread": float(r["spread"]) if "spread" in rates.dtype.names else None,
                "real_volume": float(r["real_volume"]) if "real_volume" in rates.dtype.names else None,
            }
        )
    # Warm-up = completed H1 with close_time <= eval_day 00:00
    warmup = [b for b in bars if b["close_time_utc"] <= eval_start.strftime("%Y-%m-%d %H:%M:%S")]
    return {
        "ok": True,
        "bars": bars,
        "warmup_bars": warmup[-warmup_bars:] if len(warmup) >= warmup_bars else warmup,
        "n_warmup_available": len(warmup),
        "n": len(bars),
        "elapsed_s": elapsed,
        "requested_start": start.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_end": end.strftime("%Y-%m-%d %H:%M:%S"),
        "actual_start": bars[0]["timestamp_utc"] if bars else None,
        "actual_end": bars[-1]["timestamp_utc"] if bars else None,
        "mt5_error": handle.last_error(),
        "warmup_sufficient": len(warmup) >= warmup_bars,
    }


def fetch_ticks_hour(
    handle: Any,
    symbol: str,
    day: str,
    hour: int,
    *,
    wall_deadline: float,
) -> dict[str, Any]:
    if time.monotonic() > wall_deadline:
        return {"ok": False, "error": "wall_budget", "ticks": [], "n": 0, "elapsed_s": 0.0, "empty": False}
    start = datetime.strptime(day, "%Y-%m-%d").replace(hour=hour, minute=0, second=0, tzinfo=UTC)
    end = start + timedelta(hours=1) - timedelta(milliseconds=1)
    t0 = time.perf_counter()
    ticks = handle.copy_ticks_range(symbol, start, end, handle.COPY_TICKS_ALL)
    elapsed = time.perf_counter() - t0
    req_s = start.strftime("%Y-%m-%d %H:%M:%S")
    req_e = end.strftime("%Y-%m-%d %H:%M:%S")
    if ticks is None:
        return {
            "ok": False,
            "error": f"copy_ticks_range: {handle.last_error()}",
            "ticks": [],
            "n": 0,
            "elapsed_s": elapsed,
            "empty": False,
            "requested_start": req_s,
            "requested_end": req_e,
            "mt5_error": handle.last_error(),
        }
    names = set(ticks.dtype.names or ())
    rows = []
    for row in ticks:
        msc = int(row["time_msc"]) if "time_msc" in names else int(row["time"]) * 1000
        bid = float(row["bid"]) if "bid" in names else None
        ask = float(row["ask"]) if "ask" in names else None
        rows.append(
            {
                "timestamp_msc": msc,
                "timestamp_utc": datetime.fromtimestamp(msc / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "bid": bid,
                "ask": ask,
                "last": float(row["last"]) if "last" in names else None,
                "volume": float(row["volume"]) if "volume" in names else None,
                "volume_real": float(row["volume_real"]) if "volume_real" in names else None,
                "flags": int(row["flags"]) if "flags" in names else None,
            }
        )
    return {
        "ok": True,
        "ticks": rows,
        "n": len(rows),
        "empty": len(rows) == 0,
        "elapsed_s": elapsed,
        "requested_start": req_s,
        "requested_end": req_e,
        "actual_start": rows[0]["timestamp_utc"] if rows else None,
        "actual_end": rows[-1]["timestamp_utc"] if rows else None,
        "mt5_error": handle.last_error(),
        "bid_ask_ok": all(r["bid"] is not None and r["ask"] is not None and r["bid"] > 0 and r["ask"] >= r["bid"] for r in rows)
        if rows
        else True,
    }
