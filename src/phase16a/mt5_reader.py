"""Read-only MT5 bar reader for Phase 16A. Allowlisted APIs only.

MetaTrader5 is imported only inside functions. No orders. No symbol_select.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase12.bar_validator import require_completed, validate_ohlc
from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase12.timestamp_normalizer import add_minutes_utc, normalize
from phase16a.constants import BAR_MINUTES, SERVER_TZ, SYMBOL, TIME_FORMAT

UTC = timezone.utc


class Mt5ReaderError(RuntimeError):
    pass


def _fmt_rate_wallclock(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=UTC).strftime(TIME_FORMAT)


def detect_timestamp_mode(handle: Any, *, as_of_utc: str) -> dict[str, Any]:
    """Choose UTC vs Europe/Athens labeling from completed-bar proximity to as_of."""
    rates = handle.copy_rates_from_pos(SYMBOL, handle.TIMEFRAME_M5, 0, 5)
    if rates is None or len(rates) == 0:
        raise Mt5ReaderError(f"timestamp probe failed: {handle.last_error()}")
    as_of = datetime.strptime(as_of_utc, TIME_FORMAT).replace(tzinfo=UTC)
    # Candidate: treat rate time as UTC wall clock
    last = rates[-1]
    open_utc = datetime.fromtimestamp(int(last["time"]), tz=UTC)
    # Forming bar open should be <= as_of and within ~10 minutes typically
    delta_sec = abs((open_utc - as_of).total_seconds())
    if delta_sec <= 15 * 60:
        return {
            "mode": "UTC",
            "already_utc": True,
            "tz_name": "UTC",
            "probe_delta_sec": delta_sec,
            "note": "rate timestamps align with UTC within 15m",
        }
    return {
        "mode": "Europe/Athens",
        "already_utc": False,
        "tz_name": SERVER_TZ,
        "probe_delta_sec": delta_sec,
        "note": "rate timestamps treated as Europe/Athens server wall clock",
    }


def open_readonly(terminal_path: str) -> dict[str, Any]:
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        return {"status": "unavailable", "reason": f"MetaTrader5 import failed: {exc}"}
    if not mt5.initialize(path=terminal_path, timeout=60000):
        return {"status": "unavailable", "reason": f"initialize failed: {mt5.last_error()}"}
    info = mt5.terminal_info()
    account = mt5.account_info()
    symbol = mt5.symbol_info(SYMBOL)
    if symbol is None:
        mt5.shutdown()
        return {"status": "symbol_unavailable", "reason": f"{SYMBOL} not available"}
    return {
        "status": "connected_readonly",
        "handle": mt5,
        "server": getattr(account, "server", None) if account else None,
        "terminal_connected": bool(getattr(info, "connected", False)) if info else False,
        "trade_mode": getattr(account, "trade_mode", None) if account else None,
        "allowlist": sorted(PERMITTED_MT5_API),
        "denylist": sorted(PROHIBITED_MT5_API),
        "note": "observation only; no orders; Market Watch not mutated",
    }


def close_readonly(handle: Any) -> None:
    if handle is None:
        return
    try:
        handle.shutdown()
    except Exception:
        pass


def _rates_to_bars(
    rates: Any,
    *,
    as_of_utc: str,
    timeframe_minutes: int,
    ts_mode: dict[str, Any],
) -> list[dict]:
    bars: list[dict] = []
    if rates is None:
        return bars
    for row in rates:
        wall = _fmt_rate_wallclock(int(row["time"]))
        meta = normalize(
            wall,
            ts_mode["tz_name"],
            already_utc=bool(ts_mode.get("already_utc")),
        )
        open_utc = meta["utc"]
        close_utc = add_minutes_utc(open_utc, timeframe_minutes)
        bar = {
            "bar_open_timestamp_utc": open_utc,
            "bar_close_timestamp_utc": close_utc,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "tick_volume": float(row["tick_volume"]),
            "spread": float(row["spread"]) if hasattr(row, "dtype") and "spread" in row.dtype.names else 0.0,
            "complete": close_utc < as_of_utc,
            "fabricated": False,
            "source_timezone": meta["source_timezone"],
            "conversion": meta["conversion"],
            "source_stamp": meta["source_stamp"],
            "data_source": "mt5_readonly_copy_rates",
        }
        validate_ohlc(bar)
        if bar["complete"]:
            require_completed(bar, as_of_utc=as_of_utc)
            bars.append(bar)
    return bars


def fetch_completed_m5(
    handle: Any,
    *,
    count: int,
    as_of_utc: str,
    ts_mode: dict[str, Any],
) -> list[dict]:
    rates = handle.copy_rates_from_pos(SYMBOL, handle.TIMEFRAME_M5, 0, int(count))
    if rates is None:
        raise Mt5ReaderError(f"copy_rates_from_pos M5 failed: {handle.last_error()}")
    return _rates_to_bars(
        rates, as_of_utc=as_of_utc, timeframe_minutes=BAR_MINUTES, ts_mode=ts_mode
    )


def fetch_completed_h1(
    handle: Any,
    *,
    count: int,
    as_of_utc: str,
    ts_mode: dict[str, Any],
) -> list[dict]:
    rates = handle.copy_rates_from_pos(SYMBOL, handle.TIMEFRAME_H1, 0, int(count))
    if rates is None:
        raise Mt5ReaderError(f"copy_rates_from_pos H1 failed: {handle.last_error()}")
    return _rates_to_bars(rates, as_of_utc=as_of_utc, timeframe_minutes=60, ts_mode=ts_mode)


def now_utc_stamp() -> str:
    return datetime.now(UTC).strftime(TIME_FORMAT)


def h1_rows_for_trend(bars: list[dict]) -> list[dict]:
    return [{"time": b["bar_open_timestamp_utc"], "close": b["close"]} for b in bars]
