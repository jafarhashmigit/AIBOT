"""Minimum decision-time NY flag + approved SELL outcomes. No extra predictors."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from phase5.constants import (
    APPROVED_M5_START,
    ATR_PERIOD,
    BAR_MINUTES,
    EXTRA_COST_PER_SIDE,
    HORIZON_BARS,
    INDEPENDENT_FEATURES,
    INDEPENDENT_OUTCOMES,
    LONDON_END_HOUR,
    LONDON_START_HOUR,
    LONDON_TZ,
    MIN_SPREAD_POINTS,
    NY_END_HOUR,
    NY_START_HOUR,
    NY_TZ,
    POINT_SIZE,
    RESEARCH_CUTOFF,
    SERVER_TZ,
    SL_ATR_MULTIPLE,
    TIME_FORMAT,
    TP_ATR_MULTIPLE,
)


def _ewm_adjust_false(values: np.ndarray, alpha: float, min_periods: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) == 0:
        return out
    prev = values[0]
    out[0] = prev
    for i in range(1, len(values)):
        prev = (1.0 - alpha) * prev + alpha * values[i]
        out[i] = prev
    out[: min_periods - 1] = np.nan
    return out


def atr14(high, low, close) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = np.nan
    tr = np.nanmax(np.vstack([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ]), axis=0)
    return _ewm_adjust_false(tr, 1.0 / ATR_PERIOD, ATR_PERIOD)


def ny_exclusive_flags(times: list[datetime]) -> np.ndarray:
    athens = ZoneInfo(SERVER_TZ)
    ny = ZoneInfo(NY_TZ)
    london = ZoneInfo(LONDON_TZ)
    flags = np.zeros(len(times), dtype=bool)
    for i, t in enumerate(times):
        local = t.replace(tzinfo=athens)
        utc = local.astimezone(ZoneInfo("UTC"))
        ny_hour = utc.astimezone(ny).hour
        london_hour = utc.astimezone(london).hour
        in_ny = NY_START_HOUR <= ny_hour < NY_END_HOUR
        in_london = LONDON_START_HOUR <= london_hour < LONDON_END_HOUR
        flags[i] = bool(in_ny and not in_london)
    return flags


def window_status(dts: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    n = len(dts)
    step = timedelta(minutes=BAR_MINUTES)
    contiguous = np.zeros(n, dtype=bool)
    contiguous[0] = False
    for i in range(1, n):
        contiguous[i] = (dts[i] - dts[i - 1]) == step
    positions = np.arange(n)
    incomplete = positions + HORIZON_BARS > n - 1
    crosses = np.zeros(n, dtype=bool)
    for offset in range(1, HORIZON_BARS + 1):
        k = np.minimum(positions + offset, n - 1)
        crosses |= ~contiguous[k]
    crosses &= ~incomplete
    return incomplete, crosses


def simulate_sell(m: dict, signal_pos: int, atr: float) -> dict:
    entry_pos = signal_pos + 1
    last_pos = entry_pos + HORIZON_BARS - 1
    tp_dist, sl_dist = TP_ATR_MULTIPLE * atr, SL_ATR_MULTIPLE * atr
    entry_fill = m["open"][entry_pos] - EXTRA_COST_PER_SIDE
    tp_level, sl_level = entry_fill - tp_dist, entry_fill + sl_dist
    exit_fill, reason = None, "TIME"
    exit_pos = last_pos
    for k in range(entry_pos, last_pos + 1):
        ask_cost = m["spread"][k] + EXTRA_COST_PER_SIDE
        open_px = m["open"][k] + ask_cost
        high_px = m["high"][k] + ask_cost
        low_px = m["low"][k] + ask_cost
        if k > entry_pos and open_px >= sl_level:
            exit_fill, reason, exit_pos = open_px, "SL", k
            break
        if high_px >= sl_level:
            exit_fill, reason, exit_pos = sl_level, "SL", k
            break
        if low_px <= tp_level:
            exit_fill, reason, exit_pos = tp_level, "TP", k
            break
    if exit_fill is None:
        exit_fill = m["close"][last_pos] + m["spread"][last_pos] + EXTRA_COST_PER_SIDE
        exit_pos = last_pos
        reason = "TIME"
    net = entry_fill - exit_fill
    costs = m["spread"][exit_pos] + 2 * EXTRA_COST_PER_SIDE
    return {
        "entry_pos": entry_pos,
        "exit_pos": exit_pos,
        "entry_fill": float(entry_fill),
        "tp_level": float(tp_level),
        "sl_level": float(sl_level),
        "exit_reason": reason,
        "gross_pnl": float(net + costs),
        "costs": float(costs),
        "net_pnl": float(net),
        "initial_risk": float(sl_dist),
        "net_r": float(net / sl_dist),
    }


def reconstruct(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    dts = [datetime.strptime(r["time"], TIME_FORMAT) for r in rows]
    n = len(rows)
    open_ = np.array([r["open"] for r in rows], float)
    high = np.array([r["high"] for r in rows], float)
    low = np.array([r["low"] for r in rows], float)
    close = np.array([r["close"] for r in rows], float)
    spread = np.maximum(np.array([r["spread"] for r in rows], float), MIN_SPREAD_POINTS) * POINT_SIZE
    atr = atr14(high, low, close)
    ny = ny_exclusive_flags(dts)
    incomplete, crosses = window_status(dts)
    m = {"open": open_, "high": high, "low": low, "close": close, "spread": spread}

    features, outcomes = [], []
    for i in range(n):
        stamp = rows[i]["time"]
        if stamp >= APPROVED_M5_START or stamp >= RESEARCH_CUTOFF:
            raise RuntimeError("independent reconstruction reached approved/cutoff stamp")
        feat = {
            "decision_time": stamp,
            "corrected_session_new_york_exclusive": int(ny[i]),
            "atr_14": None if not np.isfinite(atr[i]) else float(atr[i]),
            "eligible_window": int(not incomplete[i] and not crosses[i] and np.isfinite(atr[i]) and atr[i] > 0),
            "incomplete_window": int(incomplete[i]),
            "crosses_gap": int(crosses[i]),
        }
        features.append(feat)
        if not ny[i]:
            continue
        eligible = bool(feat["eligible_window"])
        rec = {
            "decision_time": stamp,
            "side": "SELL",
            "eligible": eligible,
            "incomplete_window": bool(incomplete[i]),
            "crosses_gap": bool(crosses[i]),
            "entry_time": "",
            "entry_fill": "",
            "stop_price": "",
            "target_price": "",
            "exit_time": "",
            "exit_reason": "",
            "gross_pnl": "",
            "costs": "",
            "net_pnl": "",
            "initial_risk": "",
            "net_r": "",
        }
        if eligible:
            tr = simulate_sell(m, i, float(atr[i]))
            rec.update({
                "entry_time": rows[tr["entry_pos"]]["time"],
                "entry_fill": tr["entry_fill"],
                "stop_price": tr["sl_level"],
                "target_price": tr["tp_level"],
                "exit_time": rows[tr["exit_pos"]]["time"],
                "exit_reason": tr["exit_reason"],
                "gross_pnl": tr["gross_pnl"],
                "costs": tr["costs"],
                "net_pnl": tr["net_pnl"],
                "initial_risk": tr["initial_risk"],
                "net_r": tr["net_r"],
            })
        outcomes.append(rec)
    return features, outcomes


def write_csv(path, rows: list[dict]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
