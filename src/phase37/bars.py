"""M5 bar retrieval + gap / OHLC validation (no fabrication)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc
M5_SECONDS = 300


def _epoch_to_utc(epoch: int) -> datetime:
    return datetime.fromtimestamp(int(epoch), tz=UTC)


def rates_to_bars(rates: Any) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    if rates is None:
        return bars
    for row in rates:
        bars.append(
            {
                "time_epoch": int(row["time"]),
                "time_utc": _epoch_to_utc(int(row["time"])).strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": float(row["tick_volume"]),
                "spread": float(row["spread"]) if "spread" in getattr(rates, "dtype").names else None,
                "real_volume": float(row["real_volume"]) if "real_volume" in getattr(rates, "dtype").names else None,
            }
        )
    return bars


def analyze_m5_bars(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if not bars:
        return {
            "n_bars": 0,
            "pass_ohlc": False,
            "pass_chrono": False,
            "reason": "no_bars",
        }
    times = [b["time_epoch"] for b in bars]
    dup = len(times) - len(set(times))
    ooo = sum(1 for i in range(1, len(times)) if times[i] < times[i - 1])
    invalid_ohlc = 0
    zero_or_neg_range = 0
    for b in bars:
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        if not (h >= max(o, c) and l <= min(o, c) and h >= l):
            invalid_ohlc += 1
        if (h - l) <= 0:
            zero_or_neg_range += 1

    gaps = []
    expected_session_gaps = 0
    unexpected_gaps = 0
    for i in range(1, len(times)):
        delta = times[i] - times[i - 1]
        if delta == M5_SECONDS:
            continue
        if delta <= 0:
            continue
        gaps.append(delta)
        # Weekend / daily break heuristic: gap >= 30m treated as session gap candidate
        if delta >= 30 * 60:
            expected_session_gaps += 1
        else:
            unexpected_gaps += 1

    avg_gap = (sum(gaps) / len(gaps)) if gaps else 0.0
    largest_gap = max(gaps) if gaps else 0

    return {
        "n_bars": len(bars),
        "first_timestamp_utc": bars[0]["time_utc"],
        "last_timestamp_utc": bars[-1]["time_utc"],
        "duplicate_timestamps": dup,
        "out_of_order_timestamps": ooo,
        "invalid_ohlc": invalid_ohlc,
        "zero_or_negative_ranges": zero_or_neg_range,
        "missing_intervals_count": len(gaps),
        "largest_gap_seconds": largest_gap,
        "average_gap_seconds": avg_gap,
        "expected_trading_session_gaps_ge_30m": expected_session_gaps,
        "unexpected_gaps_lt_30m": unexpected_gaps,
        "pass_ohlc": invalid_ohlc == 0,
        "pass_chrono": ooo == 0 and dup == 0,
        "gaps_detectable_without_fabrication": True,
    }


def fetch_m5_range(
    handle: Any,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    wall_deadline: float | None = None,
) -> dict[str, Any]:
    if wall_deadline is not None and time.monotonic() > wall_deadline:
        return {"ok": False, "error": "wall_budget", "bars": [], "elapsed_s": 0.0}
    t0 = time.perf_counter()
    rates = handle.copy_rates_range(symbol, handle.TIMEFRAME_M5, start_utc, end_utc)
    elapsed = time.perf_counter() - t0
    if rates is None:
        return {
            "ok": False,
            "error": f"copy_rates_range failed: {handle.last_error()}",
            "bars": [],
            "elapsed_s": elapsed,
            "n": 0,
        }
    bars = rates_to_bars(rates)
    analysis = analyze_m5_bars(bars)
    return {
        "ok": True,
        "symbol": symbol,
        "requested_start_utc": start_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_end_utc": end_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "bars": bars,
        "n": len(bars),
        "elapsed_s": elapsed,
        "records_per_s": (len(bars) / elapsed) if elapsed > 0 else None,
        "analysis": analysis,
        "last_error": handle.last_error(),
    }
