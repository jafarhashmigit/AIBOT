"""Phase57 fixtures — reuse Phase56 directional paths; add malformed cases."""

from __future__ import annotations

from typing import Any

from phase56.tests.fixtures import directional_path


def clean_bundle(**kw):
    return directional_path(**kw)


def malformed_price_bundle() -> tuple[str, list, list, dict]:
    day, m5, h1, by = directional_path(day="2099-07-01")
    # Inject zero/negative on a mid bar for validation (not used as entry without checks)
    ts = str(m5[30]["timestamp_utc"])
    m5[30]["close"] = 0.0
    m5[30]["low"] = -1.0
    by[ts] = [{"epoch_ms": 1, "timestamp_utc": ts, "bid": 0.0, "ask": -0.1}]
    return day, m5, h1, by


def gap_bundle() -> tuple[str, list, list, dict]:
    day, m5, h1, by = directional_path(day="2099-07-02", n_bars=60)
    # Create chronological hole by deleting bars 20-22 from processing perspective —
    # keep list but mark timestamps jumping (replace bar 21 timestamp far ahead)
    m5[21]["timestamp_utc"] = "2099-07-02 20:00:00"
    return day, m5, h1, by


def conflicting_duplicate_bar(bar: dict[str, Any]) -> dict[str, Any]:
    return {**bar, "close": float(bar["close"]) + 9.99}
