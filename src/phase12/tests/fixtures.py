"""SYNTHETIC forward bars for isolated tests. Not live market data. Not holdout."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

LABEL = "SYNTHETIC — isolated unit test; not a live observation"
SYNTHETIC = True
UTC = timezone.utc
START = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def bar_at(i: int, *, complete: True | bool = True, **overrides) -> dict:
    open_dt = START + timedelta(minutes=5 * i)
    close_dt = open_dt + timedelta(minutes=5)
    row = {
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "bar_open": _fmt(open_dt),
        "bar_close": _fmt(close_dt),
        "already_utc": True,
        "source_timezone": "UTC",
        "open": 4000.0 + i,
        "high": 4000.5 + i,
        "low": 3999.5 + i,
        "close": 4000.2 + i,
        "tick_volume": 10 + i,
        "spread": 0.2,
        "complete": complete,
        "fabricated": False,
    }
    row.update(overrides)
    return row


def continuous_bars(n: int = 20) -> list[dict]:
    return [bar_at(i) for i in range(n)]


def replay_as_of() -> str:
    last_close = START + timedelta(minutes=5 * 20)
    return _fmt(last_close + timedelta(minutes=5))


def created_at() -> str:
    return "2026-11-02T12:00:00Z"
