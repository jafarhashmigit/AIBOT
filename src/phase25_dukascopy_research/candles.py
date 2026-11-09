"""Build M5 OHLC from Dukascopy ticks without fabricating missing bars."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from phase24.adapter import NormalizedCandle, normalize_candle, validate_series
from phase25.constants import M5_DIR, SOURCE_ID, SYMBOL, TIMEFRAME

UTC = timezone.utc
Side = Literal["bid", "ask", "mid"]


def floor_m5(ts: datetime) -> datetime:
    return ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)


def build_m5_from_ticks(ticks: list[dict[str, Any]], *, side: Side = "mid") -> list[NormalizedCandle]:
    """Aggregate ticks into M5 bars. Gaps are omitted (not fabricated)."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in ticks:
        dt = datetime.strptime(t["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        # If ms precision available prefer epoch
        if "epoch_ms" in t:
            dt = datetime.fromtimestamp(t["epoch_ms"] / 1000.0, tz=UTC)
        key = floor_m5(dt).strftime("%Y-%m-%d %H:%M:%S")
        buckets[key].append(t)

    candles: list[NormalizedCandle] = []
    for open_ts in sorted(buckets):
        rows = sorted(buckets[open_ts], key=lambda r: r.get("epoch_ms", 0))
        prices = [float(r[side]) for r in rows]
        spreads = [float(r["spread"]) for r in rows if r.get("spread") is not None]
        bids = [float(r["bid"]) for r in rows]
        asks = [float(r["ask"]) for r in rows]
        vol = sum(float(r.get("bid_volume") or 0) + float(r.get("ask_volume") or 0) for r in rows)
        candles.append(
            normalize_candle(
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                timestamp_utc=open_ts,
                open_=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=vol,
                bid=bids[-1],
                ask=asks[-1],
                spread=(sum(spreads) / len(spreads)) if spreads else (asks[-1] - bids[-1]),
                source_id=f"{SOURCE_ID}_{side}",
            )
        )
    return candles


def write_m5_jsonl(candles: list[NormalizedCandle], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in candles:
            f.write(json.dumps(c.to_dict(), sort_keys=True) + "\n")


def build_and_validate_day(ticks: list[dict[str, Any]], *, day: str, side: Side = "mid") -> dict[str, Any]:
    candles = build_m5_from_ticks(ticks, side=side)
    # as_of after last possible bar of day
    as_of = f"{day} 23:59:59"
    # better: day+1 00:00:01 if needed — use end+5m
    if candles:
        last = candles[-1].timestamp_utc
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S") + __import__("datetime").timedelta(minutes=5, seconds=1)
        as_of = last_dt.strftime("%Y-%m-%d %H:%M:%S")
    validated = validate_series(candles, as_of_utc=as_of)
    out_path = M5_DIR / f"{day}_{side}.jsonl"
    write_m5_jsonl(candles, out_path)
    return {
        "day": day,
        "side": side,
        "n_ticks": len(ticks),
        "n_m5": len(candles),
        "accepted": validated["accepted_count"],
        "rejected": validated["rejected_count"],
        "issue_codes": sorted({i["code"] for i in validated["issues"]}),
        "path": str(out_path),
        "candles": candles,
    }
