"""Decision-time orthogonal features from completed OHLC bars (no lookahead)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np

from phase26.features import compute_orthogonal_features
from phase28.constants import FROZEN_VOL_FEATURES
from phase28.frozen_vol import feature_vector_at_index, predict_vol_and_regime


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def wilder_atr_series(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n < period:
        return atr
    atr[period - 1] = float(np.mean(tr[:period]))
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def bars_to_m5_context(m5_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Build Phase-26-compatible m5 dict from completed MT5-style bars."""
    rows = []
    times = []
    opens = [float(b["open"]) for b in m5_bars]
    highs = np.asarray([float(b["high"]) for b in m5_bars], dtype=float)
    lows = np.asarray([float(b["low"]) for b in m5_bars], dtype=float)
    closes = np.asarray([float(b["close"]) for b in m5_bars], dtype=float)
    atr = wilder_atr_series(highs, lows, closes, 14)
    for i, b in enumerate(m5_bars):
        t = b.get("bar_close_timestamp_utc") or b.get("time")
        if not t:
            raise ValueError("bar missing close/time")
        times.append(str(t))
        gap_min = 5.0
        if i > 0:
            prev_open = m5_bars[i - 1]["bar_open_timestamp_utc"]
            cur_open = b["bar_open_timestamp_utc"]
            gap_min = (_parse(cur_open) - _parse(prev_open)).total_seconds() / 60.0
        rows.append(
            {
                "time": str(t),
                "open": opens[i],
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "atr_14": float(atr[i]) if np.isfinite(atr[i]) else float("nan"),
                "is_after_gap": 1.0 if gap_min > 5.0 + 1e-9 else 0.0,
                "minutes_since_prev_bar": float(gap_min),
            }
        )
    return {"times": times, "rows": rows, "index": {t: i for i, t in enumerate(times)}}


def h1_bars_to_rows(h1_bars: list[dict[str, Any]]) -> list[dict]:
    out = []
    for b in h1_bars:
        t = b.get("bar_open_timestamp_utc") or b.get("time")
        out.append(
            {
                "time": str(t),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
            }
        )
    out.sort(key=lambda r: r["time"])
    return out


def predict_vol_at_bar(
    *,
    m5_bars: list[dict[str, Any]],
    h1_bars: list[dict[str, Any]],
    decision_close_utc: str,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    """Predict fwd_vol_12 + regime using only bars available at decision close."""
    # Keep bars whose close <= decision time (completed and known).
    usable = []
    for b in sorted(m5_bars, key=lambda x: x["bar_open_timestamp_utc"]):
        close = b.get("bar_close_timestamp_utc")
        if close and close <= decision_close_utc:
            usable.append(b)
    if not usable:
        return {"ok": False, "reason": "no_usable_m5_bars"}

    # H1: only fully closed H1 bars (open+1h <= decision)
    h1_usable = []
    for b in h1_bars:
        open_ts = b.get("bar_open_timestamp_utc") or b.get("time")
        if not open_ts:
            continue
        close_h1 = (_parse(str(open_ts)) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        if close_h1 <= decision_close_utc:
            h1_usable.append(b)

    m5 = bars_to_m5_context(usable)
    feats = compute_orthogonal_features(m5, h1_bars_to_rows(h1_usable))
    i = len(m5["times"]) - 1
    if m5["times"][i] != decision_close_utc:
        # allow match by last usable close
        if decision_close_utc not in m5["index"]:
            return {"ok": False, "reason": "decision_bar_not_in_context"}
        i = m5["index"][decision_close_utc]

    vec = feature_vector_at_index(feats, i)
    if vec is None:
        return {
            "ok": False,
            "reason": "feature_nan",
            "feature_names": list(FROZEN_VOL_FEATURES),
        }
    pred = predict_vol_and_regime(vec, artifact)
    return {
        "ok": True,
        "pred_fwd_vol_12": pred["pred_fwd_vol_12"],
        "pred_vol_regime": pred["pred_vol_regime"],
        "n_m5_context": len(usable),
        "n_h1_context": len(h1_usable),
        "feature_names": list(FROZEN_VOL_FEATURES),
    }
