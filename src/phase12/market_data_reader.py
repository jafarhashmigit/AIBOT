"""Read-only market data interface. Stage A uses synthetic fixtures only."""

from __future__ import annotations

from phase12.bar_validator import assert_not_fabricated, gap_status, require_completed, validate_ohlc
from phase12.timestamp_normalizer import normalize
from phase12.validation import (
    BROKER_ORDERS,
    LIVE_MARKET_REQUESTS,
    MT5_CONNECTIONS,
    SYMBOL,
    TIMEFRAME,
    ShadowError,
)


class MarketDataError(ShadowError):
    pass


class SyntheticReader:
    """Offline fixture source. Never connects to MT5."""

    def __init__(self, bars: list[dict]) -> None:
        self._bars = list(bars)
        self.errors: list[str] = []
        self.live_requests = 0
        self.mt5_connections = 0

    def poll_completed(self, *, as_of_utc: str, previous_open_utc: str | None) -> list[dict]:
        out = []
        prev = previous_open_utc
        for raw in self._bars:
            try:
                assert_not_fabricated(raw)
                tz = raw.get("source_timezone")
                opened = normalize(raw["bar_open"], tz, already_utc=bool(raw.get("already_utc")))
                closed = normalize(raw["bar_close"], tz, already_utc=bool(raw.get("already_utc")))
                bar = {
                    "symbol": raw.get("symbol", SYMBOL),
                    "timeframe": raw.get("timeframe", TIMEFRAME),
                    "bar_open_timestamp_utc": opened["utc"],
                    "bar_close_timestamp_utc": closed["utc"],
                    "open": raw["open"],
                    "high": raw["high"],
                    "low": raw["low"],
                    "close": raw["close"],
                    "tick_volume": raw.get("tick_volume", 0),
                    "spread": raw.get("spread"),
                    "complete": raw.get("complete", True),
                    "data_source": "synthetic_fixture",
                    "source_timezone": opened["source_timezone"],
                    "conversion": opened["conversion"],
                    "source_stamp": opened["source_stamp"],
                }
                require_completed(bar, as_of_utc=as_of_utc)
                validate_ohlc(bar)
                bar["gap_status"] = gap_status(prev, bar["bar_open_timestamp_utc"])
                out.append(bar)
                prev = bar["bar_open_timestamp_utc"]
            except Exception as exc:
                self.errors.append(str(exc))
                if raw.get("stop_on_error"):
                    raise
        return out


def broker_order_calls() -> int:
    return BROKER_ORDERS


def mt5_connections() -> int:
    return MT5_CONNECTIONS


def live_market_requests() -> int:
    return LIVE_MARKET_REQUESTS
