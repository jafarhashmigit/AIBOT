"""Causal M5 features from reconstructed mid OHLC (decision-time safe)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _ema_series(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = []
    losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out[period] = 100.0 if avg_l == 0 else 100.0 - (100.0 / (1.0 + avg_g / avg_l))
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        out[i + 1] = 100.0 if avg_l == 0 else 100.0 - (100.0 / (1.0 + avg_g / avg_l))
    return out


def _wilder_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    out[period] = atr
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        out[i + 1] = atr
    return out


def _session_flags(ts: str) -> dict[str, int]:
    hour = int(ts[11:13])
    return {
        "corrected_session_asia": int(0 <= hour < 7),
        "corrected_session_london": int(7 <= hour < 12),
        "corrected_session_new_york": int(12 <= hour < 21),
    }


def build_features(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Return feature dict keyed by bar time; bars list for strategy lookback."""
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    ema9 = _ema_series(closes, 9)
    ema20 = _ema_series(closes, 20)
    ema50 = _ema_series(closes, 50)
    atr14 = _wilder_atr(highs, lows, closes, 14)
    rsi14 = _rsi(closes, 14)

    # realized vol proxies
    rets = [0.0] + [closes[i] / closes[i - 1] - 1.0 if closes[i - 1] else 0.0 for i in range(1, len(closes))]

    features: dict[str, dict[str, Any]] = {}
    feature_times: list[str] = []
    for i, c in enumerate(candles):
        t = c["time"]
        feature_times.append(t)
        e9, e20, e50 = ema9[i], ema20[i], ema50[i]
        atr = atr14[i]
        sess = _session_flags(t)
        vol12 = None
        vol48 = None
        if i >= 12:
            chunk = rets[i - 11 : i + 1]
            mu = sum(chunk) / len(chunk)
            vol12 = (sum((x - mu) ** 2 for x in chunk) / len(chunk)) ** 0.5
        if i >= 48:
            chunk = rets[i - 47 : i + 1]
            mu = sum(chunk) / len(chunk)
            vol48 = (sum((x - mu) ** 2 for x in chunk) / len(chunk)) ** 0.5
        feat = {
            "time": t,
            "open": opens[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "ema_9": e9,
            "ema_20": e20,
            "ema_50": e50,
            "close_to_ema_20": ((closes[i] - e20) / e20) if e20 else None,
            "ema_9_20_spread": ((e9 - e20) / e20) if (e9 is not None and e20) else None,
            "atr_14": atr,
            "atr_14_pct": (atr / closes[i]) if atr and closes[i] else None,
            "rsi_14": rsi14[i],
            "volatility_12": vol12,
            "volatility_48": vol48,
            "volatility_ratio_12_48": (vol12 / vol48) if (vol12 is not None and vol48 and vol48 > 0) else None,
            "bid_open": c["bid_open"],
            "ask_open": c["ask_open"],
            "bid_close": c["bid_close"],
            "ask_close": c["ask_close"],
            "spread_open": c["spread_open"],
            **sess,
        }
        features[t] = feat

    # H1 rows from mid close aggregation (floor to hour)
    h1_buckets: dict[str, list[float]] = {}
    for c in candles:
        hour = c["time"][:13] + ":00:00"
        # normalize: 2026-02-17 08:00:00 style — take YYYY-MM-DD HH
        ht = c["time"][:13] + ":00:00"
        h1_buckets.setdefault(ht, []).append(float(c["close"]))
    h1_rows = [{"time": ht, "close": vals[-1]} for ht, vals in sorted(h1_buckets.items())]

    return {
        "features": features,
        "feature_times": feature_times,
        "feature_index": {t: i for i, t in enumerate(feature_times)},
        "h1_rows": h1_rows,
        "candles": candles,
    }


def build_h1_series(h1_rows: list[dict]) -> list[dict]:
    """Same causal EMA20 definition as phase14.h1_trend.build_h1_series."""
    series = []
    window: list[float] = []
    ema = None
    alpha = 2.0 / 21.0
    for row in h1_rows:
        close = float(row["close"])
        window.append(close)
        if len(window) < 20:
            ema = None
        elif len(window) == 20:
            ema = sum(window) / 20.0
        else:
            ema = alpha * close + (1.0 - alpha) * float(ema)
        ot = row["time"]
        ct = (datetime.strptime(ot, "%Y-%m-%d %H:%M:%S") + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        series.append({"open_time": ot, "close_time": ct, "close": close, "ema20": ema})
    return series


def h1_trend_at(series: list[dict], decision_time: str) -> dict | None:
    lo, hi = 0, len(series) - 1
    best = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if series[mid]["close_time"] <= decision_time:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    while best >= 0 and series[best]["ema20"] is None:
        best -= 1
    if best < 0:
        return None
    bar = series[best]
    if bar["close"] > bar["ema20"]:
        trend = "up"
    elif bar["close"] < bar["ema20"]:
        trend = "down"
    else:
        trend = "flat"
    return {"h1_trend": trend, "h1_close": bar["close"], "h1_ema20": bar["ema20"], "h1_open_time": bar["open_time"]}
