"""M5 candle construction from Phase 34 ticks — no fabrication / gap fill."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc


def floor_m5(ts: str) -> str:
    dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    minute = dt.minute - (dt.minute % 5)
    return dt.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def build_m5_candles(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    """Build separate bid/ask/mid M5 OHLC. Gaps omitted (never invented)."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in ticks:
        buckets[floor_m5(t["timestamp_utc"])].append(t)

    candles: list[dict[str, Any]] = []
    for bar_ts in sorted(buckets.keys()):
        group = buckets[bar_ts]
        bids = [float(x["bid"]) for x in group]
        asks = [float(x["ask"]) for x in group]
        mids = [(b + a) / 2.0 for b, a in zip(bids, asks)]
        candles.append(
            {
                "time": bar_ts,
                "tick_count": len(group),
                "open": mids[0],
                "high": max(mids),
                "low": min(mids),
                "close": mids[-1],
                "bid_open": bids[0],
                "bid_high": max(bids),
                "bid_low": min(bids),
                "bid_close": bids[-1],
                "ask_open": asks[0],
                "ask_high": max(asks),
                "ask_low": min(asks),
                "ask_close": asks[-1],
                "spread_open": asks[0] - bids[0],
                "spread_close": asks[-1] - bids[-1],
                "first_epoch_ms": int(group[0]["epoch_ms"]),
                "last_epoch_ms": int(group[-1]["epoch_ms"]),
            }
        )

    # Contiguous index map; missing slots detected by >5 min gaps
    missing_slots = 0
    for i in range(1, len(candles)):
        prev = datetime.strptime(candles[i - 1]["time"], "%Y-%m-%d %H:%M:%S")
        cur = datetime.strptime(candles[i]["time"], "%Y-%m-%d %H:%M:%S")
        gap_min = (cur - prev).total_seconds() / 60.0
        if gap_min > 5:
            missing_slots += int(gap_min // 5) - 1

    by_time = {c["time"]: c for c in candles}
    return {
        "candles": candles,
        "by_time": by_time,
        "n_candles": len(candles),
        "inferred_missing_m5_slots": missing_slots,
        "fabricated": False,
        "gap_filled": False,
    }


def ticks_by_m5(ticks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in ticks:
        out[floor_m5(t["timestamp_utc"])].append(t)
    return dict(out)


def bar_window_complete(times: list[str], start_idx: int, n_bars: int, by_time: dict[str, Any]) -> bool:
    """True iff start_idx .. start_idx+n_bars-1 exist as consecutive 5-min steps with candles."""
    if start_idx < 0 or start_idx + n_bars > len(times):
        return False
    for i in range(start_idx, start_idx + n_bars):
        if times[i] not in by_time:
            return False
    # consecutive
    for i in range(start_idx + 1, start_idx + n_bars):
        prev = datetime.strptime(times[i - 1], "%Y-%m-%d %H:%M:%S")
        cur = datetime.strptime(times[i], "%Y-%m-%d %H:%M:%S")
        if (cur - prev).total_seconds() != 300:
            return False
    return True
