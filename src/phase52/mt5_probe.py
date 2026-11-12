"""Bounded read-only MT5 coverage/spread probes — no unbounded tick history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from phase52.constants import (
    CANDIDATE_INSTRUMENTS,
    INIT_TIMEOUT_MS,
    PROBE_END,
    PROBE_START,
    TERMINAL_PATH,
    TICK_SAMPLE_DAY,
    TICK_SAMPLE_HOURS,
    TIMEFRAMES,
)

UTC = timezone.utc
TF_MAP_NAMES = {"M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15", "H1": "TIMEFRAME_H1"}


def open_mt5() -> dict[str, Any]:
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"import:{exc}", "handle": None}
    if not mt5.initialize(path=TERMINAL_PATH, timeout=INIT_TIMEOUT_MS):
        return {"ok": False, "reason": f"init:{mt5.last_error()}", "handle": None}
    import phase52.constants as C

    C.MT5_CONNECTIONS += 1
    return {"ok": True, "handle": mt5, "server": getattr(mt5.account_info(), "server", None)}


def close_mt5(handle: Any) -> None:
    if handle is None:
        return
    try:
        handle.shutdown()
    except Exception:  # noqa: BLE001
        pass


def list_available_candidates(handle: Any) -> dict[str, Any]:
    syms = handle.symbols_get() or []
    by_name = {s.name: s for s in syms}
    rows = []
    for name in CANDIDATE_INSTRUMENTS:
        s = by_name.get(name)
        if s is None:
            rows.append({"symbol": name, "available": False})
            continue
        rows.append(
            {
                "symbol": name,
                "available": True,
                "visible": bool(s.visible),
                "trade_mode": int(s.trade_mode),
                "digits": int(s.digits),
                "point": float(s.point),
                "spread_points_snapshot": int(s.spread) if s.spread is not None else None,
                "trade_tick_size": float(getattr(s, "trade_tick_size", 0) or 0),
            }
        )
    return {"n_terminal_symbols": len(syms), "candidates": rows}


def _tf_const(handle: Any, tf: str):
    return getattr(handle, TF_MAP_NAMES[tf])


def probe_rates(handle: Any, symbol: str, timeframe: str) -> dict[str, Any]:
    """Bounded OHLC coverage over PROBE_START..PROBE_END."""
    start = datetime.strptime(PROBE_START, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(PROBE_END, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1) - timedelta(seconds=1)
    rates = handle.copy_rates_range(symbol, _tf_const(handle, timeframe), start, end)
    if rates is None:
        return {
            "ok": False,
            "symbol": symbol,
            "timeframe": timeframe,
            "error": str(handle.last_error()),
            "n_bars": 0,
        }
    n = len(rates)
    if n == 0:
        return {"ok": True, "symbol": symbol, "timeframe": timeframe, "n_bars": 0, "empty": True}

    # Gap heuristic: expected bar step seconds
    step = {"M5": 300, "M15": 900, "H1": 3600}[timeframe]
    times = [int(r["time"]) for r in rates]
    gaps = []
    for a, b in zip(times, times[1:]):
        dt = b - a
        if dt > step * 1.5:
            gaps.append(dt)
    # Volatility proxy from close returns
    closes = [float(r["close"]) for r in rates]
    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append(abs(closes[i] / closes[i - 1] - 1.0))
    spreads_pts = [float(r["spread"]) for r in rates if "spread" in rates.dtype.names]
    # Session coverage: hours present UTC
    hours = set(datetime.fromtimestamp(t, tz=UTC).hour for t in times)

    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "n_bars": n,
        "earliest_utc": datetime.fromtimestamp(times[0], tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "latest_utc": datetime.fromtimestamp(times[-1], tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "n_gap_events": len(gaps),
        "max_gap_seconds": max(gaps) if gaps else 0,
        "unique_utc_hours_present": sorted(hours),
        "n_unique_hours": len(hours),
        "mean_abs_return": (sum(rets) / len(rets)) if rets else None,
        "p95_abs_return": _pct(rets, 0.95),
        "m5_spread_points_mean": (sum(spreads_pts) / len(spreads_pts)) if spreads_pts else None,
        "m5_spread_points_median": _median(spreads_pts) if spreads_pts else None,
        "demo_note": "MetaQuotes-Demo rates/spreads ≠ live broker execution",
    }


def probe_ticks_sample(handle: Any, symbol: str) -> dict[str, Any]:
    """Sample a few hours only — not unbounded history."""
    day = datetime.strptime(TICK_SAMPLE_DAY, "%Y-%m-%d").replace(tzinfo=UTC)
    spreads = []
    hours_ok = 0
    hours_empty = 0
    hours_fail = 0
    crossed = 0
    for h in TICK_SAMPLE_HOURS:
        start = day + timedelta(hours=h)
        end = start + timedelta(hours=1) - timedelta(milliseconds=1)
        ticks = handle.copy_ticks_range(symbol, start, end, handle.COPY_TICKS_ALL)
        if ticks is None:
            hours_fail += 1
            continue
        if len(ticks) == 0:
            hours_empty += 1
            continue
        hours_ok += 1
        for t in ticks:
            bid, ask = float(t["bid"]), float(t["ask"])
            if ask < bid:
                crossed += 1
                continue
            spreads.append(ask - bid)
    return {
        "symbol": symbol,
        "sample_day": TICK_SAMPLE_DAY,
        "sample_hours": list(TICK_SAMPLE_HOURS),
        "hours_ok": hours_ok,
        "hours_empty": hours_empty,
        "hours_fail": hours_fail,
        "n_spreads": len(spreads),
        "crossed_quotes": crossed,
        "spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
        "spread_median": _median(spreads),
        "spread_p95": _pct(spreads, 0.95),
        "bid_ask_available": len(spreads) > 0,
        "demo_note": "Demo tick bid/ask sample only",
    }


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    return ys[mid] if n % 2 else 0.5 * (ys[mid - 1] + ys[mid])


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(p * (len(ys) - 1))))
    return ys[i]
