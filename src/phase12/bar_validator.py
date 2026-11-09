"""Completed-bar checks. Never fabricates missing candles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from phase12.validation import BAR_MINUTES, ShadowError, TIME_FORMAT

UTC = timezone.utc


class BarError(ShadowError):
    pass


def parse_utc(stamp: str) -> datetime:
    return datetime.strptime(stamp, TIME_FORMAT).replace(tzinfo=UTC)


def validate_ohlc(bar: dict) -> None:
    try:
        o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BarError("invalid OHLC types") from exc
    if min(o, h, l, c) <= 0:
        raise BarError("OHLC must be positive")
    if h < l:
        raise BarError("high < low")
    if h < o or h < c:
        raise BarError("high below open/close")
    if l > o or l > c:
        raise BarError("low above open/close")
    vol = float(bar.get("tick_volume", 0) or 0)
    if vol < 0:
        raise BarError("negative tick_volume")


def require_completed(bar: dict, *, as_of_utc: str) -> None:
    if bar.get("complete") is False:
        raise BarError("incomplete candle rejected")
    close = str(bar["bar_close_timestamp_utc"])
    if not (close < as_of_utc):
        raise BarError("incomplete candle: close is not strictly before as_of")


def gap_status(previous_open_utc: str | None, current_open_utc: str) -> str:
    if previous_open_utc is None:
        return "first"
    expected = parse_utc(previous_open_utc) + timedelta(minutes=BAR_MINUTES)
    actual = parse_utc(current_open_utc)
    if actual == expected:
        return "continuous"
    if actual < expected:
        raise BarError("bar timestamps went backwards")
    return "gap"


def assert_not_fabricated(bar: dict) -> None:
    if bar.get("fabricated") is True:
        raise BarError("fabricated bars are forbidden")
