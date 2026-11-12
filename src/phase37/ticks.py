"""Historical tick retrieval + bid/ask / spread validation."""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc


def _pct(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def ticks_to_rows(ticks: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if ticks is None:
        return rows
    names = set(getattr(ticks, "dtype").names or ())
    for row in ticks:
        bid = float(row["bid"]) if "bid" in names else None
        ask = float(row["ask"]) if "ask" in names else None
        spread = (ask - bid) if bid is not None and ask is not None else None
        rows.append(
            {
                "time_epoch": int(row["time"]) if "time" in names else None,
                "time_msc": int(row["time_msc"]) if "time_msc" in names else None,
                "timestamp_utc": datetime.fromtimestamp(int(row["time_msc"]) / 1000.0, tz=UTC).strftime(
                    "%Y-%m-%d %H:%M:%S.%f"
                )[:-3]
                if "time_msc" in names
                else None,
                "bid": bid,
                "ask": ask,
                "last": float(row["last"]) if "last" in names else None,
                "volume": float(row["volume"]) if "volume" in names else None,
                "volume_real": float(row["volume_real"]) if "volume_real" in names else None,
                "flags": int(row["flags"]) if "flags" in names else None,
                "spread": spread,
            }
        )
    return rows


def analyze_ticks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "n_ticks": 0,
            "bid_available": False,
            "ask_available": False,
            "pass_chrono": False,
            "pass_spread": False,
            "reason": "no_ticks",
        }
    mscs = [int(r["time_msc"]) for r in rows if r.get("time_msc") is not None]
    dup = len(mscs) - len(set(mscs))
    ooo = sum(1 for i in range(1, len(mscs)) if mscs[i] < mscs[i - 1])

    bid_ok = sum(1 for r in rows if r.get("bid") is not None and float(r["bid"]) > 0)
    ask_ok = sum(1 for r in rows if r.get("ask") is not None and float(r["ask"]) > 0)
    invalid_ba = sum(
        1
        for r in rows
        if r.get("bid") is None or r.get("ask") is None or float(r["bid"]) <= 0 or float(r["ask"]) <= 0
    )
    crossed = sum(1 for r in rows if r.get("bid") is not None and r.get("ask") is not None and float(r["bid"]) > float(r["ask"]))
    neg_spread = sum(1 for r in rows if r.get("spread") is not None and float(r["spread"]) < 0)
    zero_spread = sum(1 for r in rows if r.get("spread") is not None and float(r["spread"]) == 0)

    spreads = sorted(float(r["spread"]) for r in rows if r.get("spread") is not None)
    # hour coverage
    hours = {}
    for r in rows:
        if not r.get("timestamp_utc"):
            continue
        hour_key = r["timestamp_utc"][:13]  # YYYY-MM-DD HH
        hours[hour_key] = hours.get(hour_key, 0) + 1
    gaps = []
    for i in range(1, len(mscs)):
        d = mscs[i] - mscs[i - 1]
        if d > 60_000:  # >1 minute
            gaps.append(d)

    n = len(rows)
    duration_h = ((mscs[-1] - mscs[0]) / 3_600_000.0) if len(mscs) >= 2 else 0.0
    return {
        "n_ticks": n,
        "first_tick_utc": rows[0].get("timestamp_utc"),
        "last_tick_utc": rows[-1].get("timestamp_utc"),
        "bid_available": bid_ok == n and n > 0,
        "ask_available": ask_ok == n and n > 0,
        "bid_positive_count": bid_ok,
        "ask_positive_count": ask_ok,
        "invalid_bid_ask": invalid_ba,
        "crossed_bid_gt_ask": crossed,
        "negative_spread": neg_spread,
        "zero_spread": zero_spread,
        "duplicate_timestamps_msc": dup,
        "out_of_order_timestamps": ooo,
        "spread_median": _pct(spreads, 50),
        "spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
        "spread_p95": _pct(spreads, 95),
        "spread_p99": _pct(spreads, 99),
        "spread_min": spreads[0] if spreads else None,
        "spread_max": spreads[-1] if spreads else None,
        "hours_with_ticks": len(hours),
        "ticks_per_hour_avg": (n / duration_h) if duration_h > 0 else None,
        "ticks_per_m5_approx": (n / (duration_h * 12.0)) if duration_h > 0 else None,
        "largest_gap_ms": max(gaps) if gaps else 0,
        "gaps_gt_1min_count": len(gaps),
        "pass_chrono": ooo == 0,
        "pass_spread": crossed == 0 and neg_spread == 0 and invalid_ba == 0,
    }


def fetch_ticks_range(
    handle: Any,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    wall_deadline: float | None = None,
) -> dict[str, Any]:
    if wall_deadline is not None and time.monotonic() > wall_deadline:
        return {"ok": False, "error": "wall_budget", "ticks": [], "elapsed_s": 0.0, "n": 0}
    t0 = time.perf_counter()
    ticks = handle.copy_ticks_range(symbol, start_utc, end_utc, handle.COPY_TICKS_ALL)
    elapsed = time.perf_counter() - t0
    if ticks is None:
        return {
            "ok": False,
            "error": f"copy_ticks_range failed: {handle.last_error()}",
            "ticks": [],
            "elapsed_s": elapsed,
            "n": 0,
            "dtype_names": None,
        }
    rows = ticks_to_rows(ticks)
    analysis = analyze_ticks(rows)
    return {
        "ok": True,
        "symbol": symbol,
        "requested_start_utc": start_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_end_utc": end_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "ticks": rows,
        "n": len(rows),
        "elapsed_s": elapsed,
        "records_per_s": (len(rows) / elapsed) if elapsed > 0 else None,
        "approx_mb": (len(rows) * 64) / (1024 * 1024),
        "dtype_names": list(getattr(ticks, "dtype").names or ()),
        "analysis": analysis,
        "last_error": handle.last_error(),
    }


def day_window(day_start: datetime) -> tuple[datetime, datetime]:
    start = day_start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return start, end
