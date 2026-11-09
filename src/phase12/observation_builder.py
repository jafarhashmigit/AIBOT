"""Build forward-shadow observations from validated completed bars."""

from __future__ import annotations

from datetime import datetime, timezone

from phase12.validation import SOURCE_FORWARD, SYMBOL, TIMEFRAME, ShadowError

UTC = timezone.utc


def observation_id(open_utc: str) -> str:
    return f"fwd:{SYMBOL}:{TIMEFRAME}:{open_utc}"


def build_observation(bar: dict, *, created_at_utc: str | None = None) -> dict:
    if bar.get("symbol", SYMBOL) != SYMBOL or bar.get("timeframe", TIMEFRAME) != TIMEFRAME:
        raise ShadowError("forward observation must be XAUUSD M5")
    created = created_at_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    oid = observation_id(bar["bar_open_timestamp_utc"])
    return {
        "observation_id": oid,
        "source_type": SOURCE_FORWARD,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "bar_open_timestamp_utc": bar["bar_open_timestamp_utc"],
        "bar_close_timestamp_utc": bar["bar_close_timestamp_utc"],
        "observation_created_at_utc": created,
        "open": bar["open"],
        "high": bar["high"],
        "low": bar["low"],
        "close": bar["close"],
        "tick_volume": bar["tick_volume"],
        "spread": "" if bar.get("spread") is None else bar["spread"],
        "data_source": bar.get("data_source", "unknown"),
        "data_quality_status": "ok",
        "gap_status": bar.get("gap_status", "unknown"),
        "model_status": "NO_MODEL",
        "feature_snapshot_reference": "",
        "source_timezone": bar.get("source_timezone", ""),
        "conversion": bar.get("conversion", ""),
        "source_stamp": bar.get("source_stamp", ""),
        "decision_id": f"shadow:{oid}",
    }
