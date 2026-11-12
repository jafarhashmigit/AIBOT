"""Synthetic fixtures for SL/TP integration tests — not historical evidence."""

from __future__ import annotations

from typing import Any


def directional_path(
    *,
    day: str = "2099-06-03",
    n_bars: int = 80,
    start: float = 2000.0,
    move_after_entry: float = 0.0,
) -> tuple[str, list[dict], list[dict], dict[str, list]]:
    """Build M5 + ticks. Entry at idx 49 (decision 48). move_after_entry shifts post-entry mids."""
    m5 = []
    by: dict[str, list] = {}
    price = start
    hour, minute = 8, 0
    for i in range(n_bars):
        # Decision idx=48; entry idx=49 at pre-move; adverse/favorable move from idx=50
        if i >= 50:
            price = start + move_after_entry
        elif i == 49:
            price = start
        ts = f"{day} {hour:02d}:{minute:02d}:00"
        o = c = price
        # Wider bar ranges → larger ATR so demo spread/ATR stays tradable under risk gates
        h, l = price + 0.8, price - 0.8
        m5.append({"timestamp_utc": ts, "open": o, "high": h, "low": l, "close": c, "tick_volume": 10, "spread": 2})
        spread = 0.02
        by[ts] = [
            {
                "epoch_ms": i * 300000 + j,
                "timestamp_utc": f"{day} {hour:02d}:{minute:02d}:{j:02d}",
                "bid": price - spread / 2,
                "ask": price + spread / 2,
            }
            for j in range(3)
        ]
        if i < 48:
            price = start + (0.4 if i % 2 == 0 else -0.2)
        minute += 5
        if minute >= 60:
            minute = 0
            hour += 1
    h1 = [
        {
            "timestamp_utc": f"{day} {h:02d}:00:00",
            "open": start,
            "high": start + 1,
            "low": start - 1,
            "close": start,
        }
        for h in range(8, 16)
    ]
    return day, m5, h1, by
