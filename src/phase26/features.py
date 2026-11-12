"""Causal orthogonal feature engineering (closed-bar only)."""

from __future__ import annotations

import math
import numpy as np

from phase26.constants import ORTHOGONAL_CANDIDATES


def _f(rows: list[dict], key: str) -> np.ndarray:
    return np.asarray([float(r[key]) for r in rows], dtype=float)


def _rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1 : i + 1]
        out[i] = float(np.std(w))
    return out


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    c = np.cumsum(np.nan_to_num(x, nan=0.0))
    for i in range(n - 1, len(x)):
        if np.any(~np.isfinite(x[i - n + 1 : i + 1])):
            continue
        out[i] = (c[i] - (c[i - n] if i >= n else 0.0)) / n
        # safer:
        out[i] = float(np.mean(x[i - n + 1 : i + 1]))
    return out


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev = np.roll(close, 1)
    prev[0] = close[0]
    return np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))


def compute_orthogonal_features(m5: dict, h1_rows: list[dict]) -> dict[str, np.ndarray]:
    rows = m5["rows"]
    n = len(rows)
    close = _f(rows, "close")
    high = _f(rows, "high")
    low = _f(rows, "low")
    atr = _f(rows, "atr_14")
    logret = np.full(n, np.nan)
    logret[1:] = np.log(close[1:] / close[:-1])

    candle_range = high - low
    upper_wick = high - np.maximum(close, _f(rows, "open"))
    lower_wick = np.minimum(close, _f(rows, "open")) - low

    rv_6 = _rolling_std(logret, 6)
    rv_24 = _rolling_std(logret, 24)

    atr_accel_6 = np.full(n, np.nan)
    for i in range(6, n):
        if atr[i - 6] > 0:
            atr_accel_6[i] = atr[i] / atr[i - 6] - 1.0

    range_sma_24 = _sma(candle_range, 24)
    range_exp_24 = np.where(range_sma_24 > 0, candle_range / range_sma_24, np.nan)

    vol_persist_12 = np.full(n, np.nan)
    for i in range(24 + 11, n):
        flags = []
        for j in range(i - 11, i + 1):
            if np.isfinite(rv_6[j]) and np.isfinite(rv_24[j]):
                flags.append(1.0 if rv_6[j] > rv_24[j] else 0.0)
        if len(flags) == 12:
            vol_persist_12[i] = float(np.mean(flags))

    er_20 = np.full(n, np.nan)
    for i in range(20, n):
        change = abs(close[i] - close[i - 20])
        path = float(np.sum(np.abs(np.diff(close[i - 20 : i + 1]))))
        er_20[i] = change / path if path > 1e-12 else 0.0

    consec_dir = np.zeros(n)
    for i in range(1, n):
        d = np.sign(close[i] - close[i - 1])
        if d == 0:
            consec_dir[i] = 0.0
        elif np.sign(consec_dir[i - 1]) == d:
            consec_dir[i] = consec_dir[i - 1] + d
        else:
            consec_dir[i] = d

    ret_ac1_24 = np.full(n, np.nan)
    for i in range(25, n):
        r = logret[i - 23 : i + 1]
        if np.any(~np.isfinite(r)):
            continue
        x = r[1:]
        y = r[:-1]
        if float(np.std(x)) < 1e-15 or float(np.std(y)) < 1e-15:
            ret_ac1_24[i] = 0.0
        else:
            ret_ac1_24[i] = float(np.corrcoef(x, y)[0, 1])

    tr = _true_range(high, low, close)
    chop_14 = np.full(n, np.nan)
    for i in range(14, n):
        hh = float(np.max(high[i - 13 : i + 1]))
        ll = float(np.min(low[i - 13 : i + 1]))
        den = abs(hh - ll)
        if den <= 1e-12:
            continue
        s = float(np.sum(tr[i - 13 : i + 1]))
        chop_14[i] = 100.0 * math.log10(s / den) / math.log10(14.0)

    # Prior Donchian excluding current bar (non-repainting)
    dist_prior_high_20_atr = np.full(n, np.nan)
    dist_prior_low_20_atr = np.full(n, np.nan)
    fail_break_up = np.zeros(n)
    fail_break_dn = np.zeros(n)
    for i in range(21, n):
        ph = float(np.max(high[i - 20 : i]))
        pl = float(np.min(low[i - 20 : i]))
        if atr[i] > 0:
            dist_prior_high_20_atr[i] = (close[i] - ph) / atr[i]
            dist_prior_low_20_atr[i] = (close[i] - pl) / atr[i]
        # failed break: previous close beyond channel, current back inside
        if i >= 22:
            ph2 = float(np.max(high[i - 21 : i - 1]))
            pl2 = float(np.min(low[i - 21 : i - 1]))
            if close[i - 1] > ph2 and close[i] <= ph2:
                fail_break_up[i] = 1.0
            if close[i - 1] < pl2 and close[i] >= pl2:
                fail_break_dn[i] = 1.0

    wick_reject_up_atr = np.where(atr > 0, upper_wick / atr, np.nan)
    wick_reject_dn_atr = np.where(atr > 0, lower_wick / atr, np.nan)

    range_sma_6 = _sma(candle_range, 6)
    range_sma_48 = _sma(candle_range, 48)
    range_compression_6_48 = np.where(range_sma_48 > 0, range_sma_6 / range_sma_48, np.nan)

    # H1 context: only fully closed H1 bars (close_time <= decision time)
    h1_atr_pct = np.full(n, np.nan)
    h1_er_10 = np.full(n, np.nan)
    m5_move_vs_h1_range = np.full(n, np.nan)

    h1_times = [r["time"] for r in h1_rows]
    h1_close = np.asarray([r["close"] for r in h1_rows], dtype=float)
    h1_high = np.asarray([r["high"] for r in h1_rows], dtype=float)
    h1_low = np.asarray([r["low"] for r in h1_rows], dtype=float)
    h1_atr = np.full(len(h1_rows), np.nan)
    h1_er = np.full(len(h1_rows), np.nan)
    for i in range(14, len(h1_rows)):
        # Wilder-like simple ATR mean TR
        trs = []
        for j in range(i - 13, i + 1):
            prev_c = h1_close[j - 1] if j > 0 else h1_close[j]
            trs.append(
                max(
                    h1_high[j] - h1_low[j],
                    abs(h1_high[j] - prev_c),
                    abs(h1_low[j] - prev_c),
                )
            )
        a = float(np.mean(trs))
        if h1_close[i] > 0:
            h1_atr[i] = a / h1_close[i]
        if i >= 10:
            change = abs(h1_close[i] - h1_close[i - 10])
            path = float(np.sum(np.abs(np.diff(h1_close[i - 10 : i + 1]))))
            h1_er[i] = change / path if path > 1e-12 else 0.0

    # For each M5 bar, last completed H1: open_time + 1h <= m5 time
    from datetime import datetime, timedelta

    def _p(ts: str) -> datetime:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

    h1_close_times = [
        (_p(t) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S") for t in h1_times
    ]
    j = -1
    for i, t in enumerate(m5["times"]):
        while j + 1 < len(h1_close_times) and h1_close_times[j + 1] <= t:
            j += 1
        if j < 14:
            continue
        h1_atr_pct[i] = h1_atr[j]
        h1_er_10[i] = h1_er[j]
        hr = h1_high[j] - h1_low[j]
        if hr > 1e-12:
            # M5 close location vs completed H1 range
            m5_move_vs_h1_range[i] = (close[i] - h1_low[j]) / hr - 0.5

    feats = {
        "rv_6": rv_6,
        "rv_24": rv_24,
        "atr_accel_6": atr_accel_6,
        "range_exp_24": range_exp_24,
        "vol_persist_12": vol_persist_12,
        "er_20": er_20,
        "consec_dir": consec_dir,
        "ret_ac1_24": ret_ac1_24,
        "chop_14": chop_14,
        "dist_prior_high_20_atr": dist_prior_high_20_atr,
        "dist_prior_low_20_atr": dist_prior_low_20_atr,
        "wick_reject_up_atr": wick_reject_up_atr,
        "wick_reject_dn_atr": wick_reject_dn_atr,
        "fail_break_up": fail_break_up,
        "fail_break_dn": fail_break_dn,
        "range_compression_6_48": range_compression_6_48,
        "h1_atr_pct": h1_atr_pct,
        "h1_er_10": h1_er_10,
        "m5_move_vs_h1_range": m5_move_vs_h1_range,
        # helpers for outcomes
        "_atr": atr,
        "_close": close,
        "_high": high,
        "_low": low,
        "_open": _f(rows, "open"),
        "_gap": np.asarray([float(r.get("is_after_gap") or 0) for r in rows], dtype=float),
        "_minutes_gap": np.asarray(
            [float(r.get("minutes_since_prev_bar") or 5) for r in rows], dtype=float
        ),
    }
    assert set(ORTHOGONAL_CANDIDATES).issubset(feats.keys())
    return feats


FEATURE_FORMULAS = {
    "rv_6": "stdev(log_return, 6) past-only incl. current closed bar",
    "rv_24": "stdev(log_return, 24) past-only",
    "atr_accel_6": "atr_14[t]/atr_14[t-6]-1",
    "range_exp_24": "range[t]/SMA(range,24)",
    "vol_persist_12": "mean(rv_6>rv_24 over last 12 closed bars)",
    "er_20": "Kaufman ER: |close-close_20|/sum(|Δclose|) over 20",
    "consec_dir": "signed consecutive close direction streak",
    "ret_ac1_24": "corr(r_t, r_{t-1}) over 24 closed log returns",
    "chop_14": "100*log10(sum(TR)/|HH-LL|)/log10(14)",
    "dist_prior_high_20_atr": "(close-max(high[-20:-1]))/atr_14",
    "dist_prior_low_20_atr": "(close-min(low[-20:-1]))/atr_14",
    "wick_reject_up_atr": "upper_wick/atr_14",
    "wick_reject_dn_atr": "lower_wick/atr_14",
    "fail_break_up": "1 if prior close > prior Donchian20 high and current close back <= that high",
    "fail_break_dn": "1 if prior close < prior Donchian20 low and current close back >= that low",
    "range_compression_6_48": "SMA(range,6)/SMA(range,48)",
    "h1_atr_pct": "ATR(14)/close on last fully closed H1 bar",
    "h1_er_10": "Kaufman ER(10) on last fully closed H1 bar",
    "m5_move_vs_h1_range": "(close-h1_low)/(h1_high-h1_low)-0.5 using completed H1",
}
