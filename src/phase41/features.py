"""Causal M5 features + Phase40 completed H1 warm-up (no look-ahead)."""

from __future__ import annotations

from typing import Any

from phase35.features import _ema_series, _rsi, _session_flags, _wilder_atr, build_h1_series, h1_trend_at


def candles_from_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for b in bars:
        t = b.get("timestamp_utc") or b.get("time_utc")
        out.append(
            {
                "time": t,
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
            }
        )
    return out


def h1_rows_from_phase40(h1_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use genuine MT5 H1 open times; build_h1_series derives close_time = open+1h."""
    rows = []
    for b in sorted(h1_bars, key=lambda x: int(x["time_epoch"])):
        rows.append({"time": b["timestamp_utc"], "close": float(b["close"])})
    return rows


def build_feature_bundle(bars: list[dict[str, Any]], h1_bars: list[dict[str, Any]]) -> dict[str, Any]:
    candles = candles_from_bars(bars)
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    ema9 = _ema_series(closes, 9)
    ema20 = _ema_series(closes, 20)
    ema50 = _ema_series(closes, 50)
    atr14 = _wilder_atr(highs, lows, closes, 14)
    rsi14 = _rsi(closes, 14)
    rets = [0.0] + [closes[i] / closes[i - 1] - 1.0 if closes[i - 1] else 0.0 for i in range(1, len(closes))]

    features: dict[str, dict[str, Any]] = {}
    feature_times: list[str] = []
    for i, c in enumerate(candles):
        t = c["time"]
        feature_times.append(t)
        e9, e20 = ema9[i], ema20[i]
        atr = atr14[i]
        sess = _session_flags(t)
        vol12 = vol48 = None
        if i >= 12:
            chunk = rets[i - 11 : i + 1]
            mu = sum(chunk) / len(chunk)
            vol12 = (sum((x - mu) ** 2 for x in chunk) / len(chunk)) ** 0.5
        if i >= 48:
            chunk = rets[i - 47 : i + 1]
            mu = sum(chunk) / len(chunk)
            vol48 = (sum((x - mu) ** 2 for x in chunk) / len(chunk)) ** 0.5
        features[t] = {
            "time": t,
            "open": opens[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "ema_9": e9,
            "ema_20": e20,
            "ema_50": ema50[i],
            "close_to_ema_20": ((closes[i] - e20) / e20) if e20 else None,
            "ema_9_20_spread": ((e9 - e20) / e20) if (e9 is not None and e20) else None,
            "atr_14": atr,
            "atr_14_pct": (atr / closes[i]) if atr and closes[i] else None,
            "rsi_14": rsi14[i],
            "volatility_12": vol12,
            "volatility_48": vol48,
            "volatility_ratio_12_48": (vol12 / vol48) if (vol12 is not None and vol48 and vol48 > 0) else None,
            **sess,
        }

    h1_rows = h1_rows_from_phase40(h1_bars)
    h1_series = build_h1_series(h1_rows)
    h1_ready_at: dict[str, bool] = {}
    for t in feature_times:
        ctx = h1_trend_at(h1_series, t)
        h1_ready_at[t] = ctx is not None and ctx.get("h1_ema20") is not None

    return {
        "features": features,
        "feature_times": feature_times,
        "feature_index": {t: i for i, t in enumerate(feature_times)},
        "h1_rows": h1_rows,
        "h1_series": h1_series,
        "h1_bars_available": len(h1_rows),
        "h1_ema20_ready": sum(1 for r in h1_series if r.get("ema20") is not None),
        "h1_ready_at": h1_ready_at,
        "candles": candles,
    }


def bars_lookback(feat_bundle: dict, decision_time: str, lookback: int = 120) -> list[dict] | None:
    idx = feat_bundle["feature_index"].get(decision_time)
    if idx is None:
        return None
    start = max(0, idx - lookback + 1)
    times = feat_bundle["feature_times"][start : idx + 1]
    return [feat_bundle["features"][t] for t in times if t in feat_bundle["features"]] or None


def h1_ctx_at(feat_bundle: dict, decision_time: str) -> dict | None:
    return h1_trend_at(feat_bundle["h1_series"], decision_time)
