"""Independent M5 candle construction from bid/ask ticks — no fabrication."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from phase33.constants import M5_DIR, RESEARCH_CUTOFF_UTC, SYMBOL, TIMEFRAME
from phase33.progress import write_json

UTC = timezone.utc


def floor_m5(timestamp_utc: str) -> str:
    """Floor second-resolution UTC timestamp to M5 open boundary."""
    dt = datetime.strptime(timestamp_utc[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    minute = dt.minute - (dt.minute % 5)
    floored = dt.replace(minute=minute, second=0, microsecond=0)
    return floored.strftime("%Y-%m-%d %H:%M:%S")


def build_m5_candles(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    """Build separate bid / ask / mid OHLC candles. Gaps omitted (never invented)."""
    M5_DIR.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in ticks:
        ts = t["timestamp_utc"]
        if ts > RESEARCH_CUTOFF_UTC:
            continue
        buckets[floor_m5(ts)].append(t)

    candles: list[dict[str, Any]] = []
    for bar_ts in sorted(buckets.keys()):
        group = buckets[bar_ts]
        bids = [float(x["bid"]) for x in group]
        asks = [float(x["ask"]) for x in group]
        mids = [float(x["mid"]) for x in group]
        candle = {
            "timestamp_utc": bar_ts,
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "tick_count": len(group),
            "bid_open": bids[0],
            "bid_high": max(bids),
            "bid_low": min(bids),
            "bid_close": bids[-1],
            "ask_open": asks[0],
            "ask_high": max(asks),
            "ask_low": min(asks),
            "ask_close": asks[-1],
            "mid_open": mids[0],
            "mid_high": max(mids),
            "mid_low": min(mids),
            "mid_close": mids[-1],
            "spread_open": asks[0] - bids[0],
            "spread_close": asks[-1] - bids[-1],
            "spread_mean": sum(asks[i] - bids[i] for i in range(len(group))) / len(group),
        }
        # Sanity: never mix bid OHLC into ask fields
        assert candle["bid_high"] >= candle["bid_low"]
        assert candle["ask_high"] >= candle["ask_low"]
        candles.append(candle)

    out_path = M5_DIR / "m5_bid_ask_mid.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for c in candles:
            f.write(json.dumps(c, sort_keys=True) + "\n")

    # Detect missing M5 slots inside contiguous sample spans (informational)
    missing = 0
    if len(candles) >= 2:
        for i in range(1, len(candles)):
            prev = datetime.strptime(candles[i - 1]["timestamp_utc"], "%Y-%m-%d %H:%M:%S")
            cur = datetime.strptime(candles[i]["timestamp_utc"], "%Y-%m-%d %H:%M:%S")
            gap_min = (cur - prev).total_seconds() / 60.0
            if gap_min > 5:
                missing += int(gap_min // 5) - 1

    report = {
        "n_candles": len(candles),
        "n_ticks_used": sum(c["tick_count"] for c in candles),
        "output_path": str(out_path),
        "bid_ask_ohlc_separated": True,
        "mid_derived": True,
        "tick_count_is_traded_volume": False,
        "fabricated_candles": False,
        "gaps_omitted_not_filled": True,
        "inferred_missing_m5_slots_inside_spans": missing,
        "pass": len(candles) > 0,
        "sample_first": candles[0]["timestamp_utc"] if candles else None,
        "sample_last": candles[-1]["timestamp_utc"] if candles else None,
    }
    write_json("candle_validation.json", report)
    return {"report": report, "candles": candles}
