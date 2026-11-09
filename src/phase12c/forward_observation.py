"""Forward-only observation container. Not a Phase 6 Observation.

Phase 6 Observation.__post_init__ refuses post-cutoff timestamps. This type is an
independent Phase 12C structure for shadow journaling and adapter inputs. It does
not bypass Phase 6 cutoff checks; it simply does not call them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from phase12c.constants import RESEARCH_CUTOFF_UTC, SOURCE_FORWARD, SYMBOL, TIMEFRAME


class ForwardObservationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ForwardObservation:
    """Completed-bar forward observation for Phase 12C only."""

    timestamp: str
    bar_open_timestamp_utc: str
    bar_close_timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: float
    complete: bool = True
    symbol: str = SYMBOL
    timeframe: str = TIMEFRAME
    source_type: str = SOURCE_FORWARD
    features: dict[str, float] = field(default_factory=dict)
    spread: float | None = None
    data_quality_status: str = "ok"
    observation_id: str = ""

    def __post_init__(self) -> None:
        if self.symbol != SYMBOL or self.timeframe != TIMEFRAME:
            raise ForwardObservationError("forward observation must be XAUUSD M5")
        if self.source_type != SOURCE_FORWARD:
            raise ForwardObservationError("source_type must be FORWARD_SHADOW")
        if not self.complete:
            raise ForwardObservationError("incomplete candle rejected")
        if self.timestamp <= RESEARCH_CUTOFF_UTC:
            # Pre-cutoff timestamps are allowed for parity tests, but production
            # forward path expects post-cutoff. Both are valid synthetic inputs.
            pass
        o, h, l, c = self.open, self.high, self.low, self.close
        if min(o, h, l, c) <= 0:
            raise ForwardObservationError("OHLC must be positive")
        if h < l or h < o or h < c or l > o or l > c:
            raise ForwardObservationError("invalid OHLC geometry")
        if self.tick_volume < 0:
            raise ForwardObservationError("negative tick_volume")
        oid = self.observation_id or f"fwd12c:{self.symbol}:{self.timeframe}:{self.bar_open_timestamp_utc}"
        object.__setattr__(self, "observation_id", oid)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "timestamp": self.timestamp,
            "bar_open_timestamp_utc": self.bar_open_timestamp_utc,
            "bar_close_timestamp_utc": self.bar_close_timestamp_utc,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tick_volume": self.tick_volume,
            "spread": self.spread,
            "complete": self.complete,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "source_type": self.source_type,
            "features": dict(self.features),
            "data_quality_status": self.data_quality_status,
            "is_post_cutoff": self.timestamp > RESEARCH_CUTOFF_UTC,
        }


def from_synthetic_bar(bar: dict, *, created_features: dict | None = None) -> ForwardObservation:
    if bar.get("complete") is False:
        raise ForwardObservationError("incomplete candle rejected")
    open_ts = bar.get("bar_open_timestamp_utc") or bar.get("bar_open")
    close_ts = bar.get("bar_close_timestamp_utc") or bar.get("bar_close")
    return ForwardObservation(
        timestamp=close_ts,
        bar_open_timestamp_utc=open_ts,
        bar_close_timestamp_utc=close_ts,
        open=float(bar["open"]),
        high=float(bar["high"]),
        low=float(bar["low"]),
        close=float(bar["close"]),
        tick_volume=float(bar.get("tick_volume", 0) or 0),
        complete=bool(bar.get("complete", True)),
        features=dict(created_features or {}),
        spread=None if bar.get("spread") is None else float(bar["spread"]),
    )
