"""Cost-aware triple-barrier engine with parameterized horizon bars.

Reuses the validated Phase 5/label_m5 / backtest_rf_m5 methodology:
- entry at next bar open with spread floor + per-side costs
- TP = 1.5×ATR, SL = 1.0×ATR from entry fill
- same-candle SL checked before TP (conservative adverse)
- gap open beyond SL fills at worse open
- TIME exit at close of last horizon bar when neither barrier hit

Does NOT modify backtest_rf_m5.simulate_trade; mirrors it with horizon_bars.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from phase18.constants import (
    ATR_PERIOD,
    BAR_MINUTES,
    EXTRA_COST_PER_SIDE,
    MIN_SPREAD_POINTS,
    POINT_SIZE,
    SL_ATR_MULTIPLE,
    TP_ATR_MULTIPLE,
)

BAR = np.timedelta64(BAR_MINUTES, "m")
BUY = 1
SELL = -1


def floored_spread_usd(spread_points: float | int | None) -> float:
    pts = float(spread_points) if spread_points is not None else float(MIN_SPREAD_POINTS)
    return max(pts, float(MIN_SPREAD_POINTS)) * POINT_SIZE


def wilder_atr(highs: list[float], lows: list[float], closes: list[float], period: int = ATR_PERIOD) -> float:
    """Compute Wilder ATR ending at the last bar. Requires period+1 closes minimum."""
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        raise ValueError("insufficient bars for ATR")
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(float(tr))
    if len(trs) < period:
        raise ValueError("insufficient true ranges for ATR")
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError(f"invalid ATR: {atr!r}")
    return float(atr)


def market_arrays_from_bars(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Build simulate_trade market arrays from OHLC bar dicts (open timestamps ascending)."""
    times = []
    for b in bars:
        t = b.get("bar_open_timestamp_utc") or b.get("time")
        times.append(np.datetime64(str(t).replace("T", " ")[:19]))
    return {
        "time": np.asarray(times),
        "open": np.asarray([float(b["open"]) for b in bars], dtype=float),
        "high": np.asarray([float(b["high"]) for b in bars], dtype=float),
        "low": np.asarray([float(b["low"]) for b in bars], dtype=float),
        "close": np.asarray([float(b["close"]) for b in bars], dtype=float),
        "spread": np.asarray(
            [floored_spread_usd(b.get("spread", MIN_SPREAD_POINTS)) for b in bars],
            dtype=float,
        ),
    }


def simulate_trade_horizon(
    m: dict[str, Any],
    side: int,
    signal_pos: int,
    atr: float,
    *,
    horizon_bars: int,
) -> dict[str, Any]:
    """Mirror of backtest_rf_m5.simulate_trade with configurable horizon_bars."""
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")
    signal_time = m["time"][signal_pos]
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError(f"Invalid atr at signal {signal_time}: {atr!r}")

    entry_pos = signal_pos + 1
    last_pos = entry_pos + horizon_bars - 1
    if last_pos >= len(m["time"]):
        raise ValueError("incomplete market window for horizon")

    tp_dist, sl_dist = TP_ATR_MULTIPLE * atr, SL_ATR_MULTIPLE * atr
    for name, dist in (("TP", tp_dist), ("SL", sl_dist)):
        if not np.isfinite(dist) or dist <= 0:
            raise ValueError(f"Invalid {name} distance: {dist!r}")

    if side == BUY:
        entry_fill = m["open"][entry_pos] + m["spread"][entry_pos] + EXTRA_COST_PER_SIDE
        tp_level, sl_level = entry_fill + tp_dist, entry_fill - sl_dist
    else:
        entry_fill = m["open"][entry_pos] - EXTRA_COST_PER_SIDE
        tp_level, sl_level = entry_fill - tp_dist, entry_fill + sl_dist

    exit_fill, reason, gap_fill = None, "TIME", False
    exit_pos = last_pos
    for k in range(entry_pos, last_pos + 1):
        if side == BUY:
            open_px = m["open"][k] - EXTRA_COST_PER_SIDE
            low_px = m["low"][k] - EXTRA_COST_PER_SIDE
            high_px = m["high"][k] - EXTRA_COST_PER_SIDE
            if k > entry_pos and open_px <= sl_level:
                exit_fill, reason, gap_fill = open_px, "SL", True
            elif low_px <= sl_level:
                exit_fill, reason = sl_level, "SL"
            elif high_px >= tp_level:
                exit_fill, reason = tp_level, "TP"
        else:
            ask_cost = m["spread"][k] + EXTRA_COST_PER_SIDE
            open_px = m["open"][k] + ask_cost
            high_px = m["high"][k] + ask_cost
            low_px = m["low"][k] + ask_cost
            if k > entry_pos and open_px >= sl_level:
                exit_fill, reason, gap_fill = open_px, "SL", True
            elif high_px >= sl_level:
                exit_fill, reason = sl_level, "SL"
            elif low_px <= tp_level:
                exit_fill, reason = tp_level, "TP"
        if exit_fill is not None:
            exit_pos = k
            break
    else:
        exit_pos = last_pos
        if side == BUY:
            exit_fill = m["close"][last_pos] - EXTRA_COST_PER_SIDE
        else:
            exit_fill = m["close"][last_pos] + m["spread"][last_pos] + EXTRA_COST_PER_SIDE

    net = exit_fill - entry_fill if side == BUY else entry_fill - exit_fill
    spread_paid = m["spread"][entry_pos] if side == BUY else m["spread"][exit_pos]
    costs = spread_paid + 2 * EXTRA_COST_PER_SIDE
    steps = np.diff(m["time"][entry_pos : exit_pos + 1])

    return {
        "side": "BUY" if side == BUY else "SELL",
        "signal_pos": signal_pos,
        "entry_pos": entry_pos,
        "exit_pos": exit_pos,
        "signal_time": m["time"][signal_pos],
        "entry_time": m["time"][entry_pos],
        "exit_time": m["time"][exit_pos],
        "bars_held": exit_pos - entry_pos + 1,
        "exit_reason": reason,
        "sl_gap_fill": gap_fill,
        "crossed_gap": bool((steps != BAR).any()) if len(steps) else False,
        "atr": float(atr),
        "tp_distance": float(tp_dist),
        "sl_distance": float(sl_dist),
        "entry_fill": float(entry_fill),
        "tp_level": float(tp_level),
        "sl_level": float(sl_level),
        "exit_fill": float(exit_fill),
        "gross_pnl": float(net + costs),
        "costs": float(costs),
        "net_pnl": float(net),
        "net_pnl_r": float(net / sl_dist),
        "horizon_bars": int(horizon_bars),
    }


def side_to_int(side: str) -> int:
    s = str(side).upper()
    if s == "BUY":
        return BUY
    if s == "SELL":
        return SELL
    raise ValueError(f"side must be BUY or SELL, got {side!r}")
