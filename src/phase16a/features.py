"""Causal M5 feature helpers for live/shadow use. No pandas. No lookahead."""

from __future__ import annotations

from typing import Any


def _ema_series(closes: list[float], span: int) -> list[float | None]:
    """Match pandas ewm(span=span, adjust=False, min_periods=span)."""
    alpha = 2.0 / (span + 1.0)
    out: list[float | None] = []
    ema: float | None = None
    for i, close in enumerate(closes):
        if i + 1 < span:
            out.append(None)
            continue
        if ema is None:
            ema = sum(closes[:span]) / float(span)
        else:
            ema = alpha * close + (1.0 - alpha) * ema
        out.append(ema)
    return out


def features_at_index(closes: list[float], index: int) -> dict[str, float] | None:
    """Features for completed bar at index using only closes[0:index+1]."""
    if index < 0 or index >= len(closes):
        return None
    window = closes[: index + 1]
    if len(window) < 20:
        return None
    ema9 = _ema_series(window, 9)
    ema20 = _ema_series(window, 20)
    e9 = ema9[index]
    e20 = ema20[index]
    if e9 is None or e20 is None or e20 == 0:
        return None
    close = window[index]
    return {
        "close": float(close),
        "ema_9": float(e9),
        "ema_20": float(e20),
        "close_to_ema_20": float(close) / float(e20) - 1.0,
        "ema_9_20_spread": float(e9) / float(e20) - 1.0,
    }


def latest_features(closes: list[float]) -> dict[str, float] | None:
    if not closes:
        return None
    return features_at_index(closes, len(closes) - 1)


def market_regime(h1_ctx: dict[str, Any] | None) -> str:
    if not h1_ctx:
        return "unknown"
    return f"h1_{h1_ctx.get('h1_trend', 'unknown')}"
