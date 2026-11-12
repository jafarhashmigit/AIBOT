"""Synthetic market fixtures for isolated software tests — not historical evidence."""

from __future__ import annotations

from typing import Any


def synthetic_day(
    day: str = "2099-01-06",
    n_bars: int = 80,
    start_price: float = 2000.0,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, list]]:
    """Monotonic M5 path with bid/ask ticks. Year 2099 avoids sealed research dates."""
    m5: list[dict[str, Any]] = []
    ticks_by_bar: dict[str, list] = {}
    price = start_price
    # Build from 00:00
    hour = 8
    minute = 0
    for i in range(n_bars):
        ts = f"{day} {hour:02d}:{minute:02d}:00"
        o = price
        c = price + (0.2 if i % 2 == 0 else -0.1)
        h = max(o, c) + 0.15
        l = min(o, c) - 0.15
        m5.append(
            {
                "timestamp_utc": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "tick_volume": 100,
                "spread": 17,
            }
        )
        spread = 0.17
        mid = c
        ticks_by_bar[ts] = [
            {
                "epoch_ms": i * 300_000 + j,
                "timestamp_utc": f"{day} {hour:02d}:{minute:02d}:{j:02d}",
                "bid": mid - spread / 2,
                "ask": mid + spread / 2,
            }
            for j in range(3)
        ]
        price = c
        minute += 5
        if minute >= 60:
            minute = 0
            hour += 1

    h1 = []
    for h in range(8, 8 + max(1, n_bars // 12)):
        h1.append(
            {
                "timestamp_utc": f"{day} {h:02d}:00:00",
                "open": start_price,
                "high": start_price + 1,
                "low": start_price - 1,
                "close": start_price + 0.2,
            }
        )
    return day, m5, h1, ticks_by_bar
