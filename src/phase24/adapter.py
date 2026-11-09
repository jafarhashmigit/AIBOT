"""Provider-neutral candle contract (offline-validatable)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Protocol

UTC = timezone.utc
TIME_FMT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class NormalizedCandle:
    symbol: str
    timeframe: str
    timestamp_utc: str  # bar open UTC
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    bid: float | None
    ask: float | None
    spread: float | None
    source_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarketDataProvider(Protocol):
    """Minimal provider interface for cloud (no MT5 types)."""

    source_id: str

    def fetch_completed_m5(self, *, start_utc: str, end_utc: str) -> list[NormalizedCandle]:
        ...

    def health(self) -> dict[str, Any]:
        ...


def parse_utc(ts: str) -> datetime:
    return datetime.strptime(ts, TIME_FMT).replace(tzinfo=UTC)


def format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime(TIME_FMT)


def normalize_candle(
    *,
    symbol: str,
    timeframe: str,
    timestamp_utc: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    source_id: str,
    volume: float | None = None,
    bid: float | None = None,
    ask: float | None = None,
    spread: float | None = None,
) -> NormalizedCandle:
    return NormalizedCandle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_utc=timestamp_utc,
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=None if volume is None else float(volume),
        bid=None if bid is None else float(bid),
        ask=None if ask is None else float(ask),
        spread=None if spread is None else float(spread),
        source_id=source_id,
    )


@dataclass
class CandleIssue:
    code: str
    message: str
    timestamp_utc: str | None = None


def validate_candle(c: NormalizedCandle, *, as_of_utc: str | None = None) -> list[CandleIssue]:
    issues: list[CandleIssue] = []
    try:
        open_dt = parse_utc(c.timestamp_utc)
    except Exception:
        return [CandleIssue("INVALID_TIMESTAMP", "timestamp_utc not parseable as UTC", c.timestamp_utc)]
    if open_dt.tzinfo != UTC:
        issues.append(CandleIssue("TZ_NOT_UTC", "timestamp must be UTC", c.timestamp_utc))
    if open_dt.minute % 5 != 0 or open_dt.second != 0:
        issues.append(CandleIssue("M5_BOUNDARY", "open must align to 5-minute UTC boundary", c.timestamp_utc))
    if not (c.high >= c.low and c.high >= c.open and c.high >= c.close and c.low <= c.open and c.low <= c.close):
        issues.append(CandleIssue("OHLC_INCONSISTENT", "OHLC relationship violated", c.timestamp_utc))
    if any(x != x or x is None for x in (c.open, c.high, c.low, c.close)):  # NaN check
        issues.append(CandleIssue("OHLC_NAN", "OHLC contains NaN", c.timestamp_utc))
    if as_of_utc is not None:
        close_dt = open_dt + timedelta(minutes=5)
        as_of = parse_utc(as_of_utc)
        if not (as_of > close_dt):
            issues.append(CandleIssue("INCOMPLETE", "candle not completed relative to as_of_utc", c.timestamp_utc))
    if c.spread is not None and c.spread < 0:
        issues.append(CandleIssue("NEGATIVE_SPREAD", "spread must be >= 0 when present", c.timestamp_utc))
    if c.bid is not None and c.ask is not None and c.ask < c.bid:
        issues.append(CandleIssue("BID_ASK_INVERTED", "ask < bid", c.timestamp_utc))
    return issues


def validate_series(candles: Iterable[NormalizedCandle], *, as_of_utc: str | None = None) -> dict[str, Any]:
    rows = list(candles)
    issues: list[dict[str, Any]] = []
    accepted: list[NormalizedCandle] = []
    seen: set[str] = set()
    prev: datetime | None = None
    for c in rows:
        local = validate_candle(c, as_of_utc=as_of_utc)
        if c.timestamp_utc in seen:
            local.append(CandleIssue("DUPLICATE", "duplicate timestamp_utc", c.timestamp_utc))
        open_dt = None
        try:
            open_dt = parse_utc(c.timestamp_utc)
        except Exception:
            pass
        if prev is not None and open_dt is not None and open_dt < prev:
            local.append(CandleIssue("OUT_OF_ORDER", "timestamp before previous", c.timestamp_utc))
        if prev is not None and open_dt is not None:
            gap = open_dt - prev
            if gap > timedelta(minutes=5):
                # Flag missing candles between prev and current (weekend gaps possible).
                local.append(
                    CandleIssue(
                        "MISSING_GAP",
                        f"gap_minutes={(gap.total_seconds()/60):.0f}",
                        c.timestamp_utc,
                    )
                )
        if local:
            for i in local:
                issues.append({"code": i.code, "message": i.message, "timestamp_utc": i.timestamp_utc})
            # Reject hard errors; flag gaps but still accept OHLC-valid bars with MISSING_GAP only
            hard = {x.code for x in local} - {"MISSING_GAP"}
            if hard:
                continue
        seen.add(c.timestamp_utc)
        if open_dt is not None:
            prev = open_dt
        accepted.append(c)
    return {
        "input_count": len(rows),
        "accepted_count": len(accepted),
        "rejected_count": len(rows) - len(accepted),
        "issues": issues,
        "accepted": [c.to_dict() for c in accepted],
    }


class FixtureProvider:
    """Offline provider backed by a JSON fixture (for tests / parity)."""

    def __init__(self, source_id: str, candles: list[NormalizedCandle]) -> None:
        self.source_id = source_id
        self._candles = sorted(candles, key=lambda c: c.timestamp_utc)

    def fetch_completed_m5(self, *, start_utc: str, end_utc: str) -> list[NormalizedCandle]:
        return [c for c in self._candles if start_utc <= c.timestamp_utc <= end_utc]

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._candles else "empty",
            "source_id": self.source_id,
            "n_candles": len(self._candles),
            "live": False,
        }


def candles_from_algospecial_payload(payload: dict[str, Any], *, source_id: str = "algospecial") -> list[NormalizedCandle]:
    """Map AlgoSpecial OHLC JSON to normalized candles.

    Official docs: timestamps are broker server time (not guaranteed UTC).
    This mapper stores the raw stamp in timestamp_utc field only after
    treating the stamp as UTC for comparison experiments — callers must
    record that TZ assumption separately.
    """
    out: list[NormalizedCandle] = []
    for row in payload.get("data") or []:
        ts_raw = str(row["Timestamp"]).replace(".", "-", 2)
        out.append(
            normalize_candle(
                symbol=str(payload.get("symbol") or "XAUUSD"),
                timeframe=str(payload.get("timeframe") or "M5"),
                timestamp_utc=ts_raw,
                open_=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["TickVolume"]) if row.get("TickVolume") is not None else None,
                spread=float(row["Spread"]) if row.get("Spread") is not None else None,
                source_id=source_id,
            )
        )
    return out


def candles_from_mt5_feature_rows(rows: list[dict[str, Any]], *, source_id: str = "mt5_reference") -> list[NormalizedCandle]:
    out: list[NormalizedCandle] = []
    for row in rows:
        out.append(
            normalize_candle(
                symbol="XAUUSD",
                timeframe="M5",
                timestamp_utc=str(row["time"]),
                open_=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["tick_volume"]) if row.get("tick_volume") is not None else None,
                spread=float(row["spread"]) if row.get("spread") is not None else None,
                source_id=source_id,
            )
        )
    return out
