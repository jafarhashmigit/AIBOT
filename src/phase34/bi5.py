"""Dukascopy bi5 URL + decode (stdlib only). Independent of Phase 33 modules for immutability."""

from __future__ import annotations

import lzma
import struct
from datetime import datetime, timedelta, timezone
from typing import Any

from phase34.constants import DUKASCOPY_BASE, RESEARCH_CUTOFF_UTC, SYMBOL, XAUUSD_PRICE_SCALE

UTC = timezone.utc
TICK_STRUCT = struct.Struct(">IIIff")  # ms, ask, bid, ask_vol, bid_vol


def bi5_url(day: str, hour: int) -> str:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    return (
        f"{DUKASCOPY_BASE}/{SYMBOL}/{dt.year}/{dt.month - 1:02d}/{dt.day:02d}/{hour:02d}h_ticks.bi5"
    )


def assert_before_cutoff(day: str, hour: int) -> None:
    # Allow hours whose start is before cutoff; ticks after cutoff dropped in decode.
    ts = f"{day} {hour:02d}:00:00"
    if ts > RESEARCH_CUTOFF_UTC:
        raise RuntimeError(f"refusing hour at/after cutoff: {ts}")


def decode_ticks(body: bytes, *, day: str, hour: int) -> list[dict[str, Any]]:
    if not body:
        return []
    raw = lzma.decompress(body)
    if len(raw) % TICK_STRUCT.size != 0:
        raise ValueError(f"unexpected bi5 payload length {len(raw)}")
    hour_start = datetime.strptime(f"{day} {hour:02d}:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    out: list[dict[str, Any]] = []
    for off in range(0, len(raw), TICK_STRUCT.size):
        ms, ask_i, bid_i, ask_vol, bid_vol = TICK_STRUCT.unpack_from(raw, off)
        ts = hour_start + timedelta(milliseconds=ms)
        ts_s = ts.strftime("%Y-%m-%d %H:%M:%S")
        if ts_s > RESEARCH_CUTOFF_UTC:
            continue
        ask = ask_i / XAUUSD_PRICE_SCALE
        bid = bid_i / XAUUSD_PRICE_SCALE
        out.append(
            {
                "timestamp_utc": ts_s,
                "epoch_ms": int(ts.timestamp() * 1000),
                "bid": bid,
                "ask": ask,
                "spread": ask - bid,
                "ask_volume": float(ask_vol),
                "bid_volume": float(bid_vol),
            }
        )
    return out
