"""SYNTHETIC fixtures for Phase 12C. Not live market data. Not holdout."""

from __future__ import annotations

LABEL = "SYNTHETIC — Phase 12C unit test; not a live observation"
SYNTHETIC = True

PRE_CUTOFF_BAR = {
    "bar_open_timestamp_utc": "2026-06-19 09:55:00",
    "bar_close_timestamp_utc": "2026-06-19 10:00:00",
    "open": 3300.0,
    "high": 3301.0,
    "low": 3299.0,
    "close": 3300.5,
    "tick_volume": 12,
    "spread": 0.2,
    "complete": True,
}

POST_CUTOFF_BAR = {
    "bar_open_timestamp_utc": "2026-11-02 09:55:00",
    "bar_close_timestamp_utc": "2026-11-02 10:00:00",
    "open": 4000.0,
    "high": 4001.0,
    "low": 3999.0,
    "close": 4000.5,
    "tick_volume": 15,
    "spread": 0.2,
    "complete": True,
}

INCOMPLETE_BAR = {
    **POST_CUTOFF_BAR,
    "complete": False,
}

INVALID_OHLC_BAR = {
    **POST_CUTOFF_BAR,
    "high": 3990.0,
}
