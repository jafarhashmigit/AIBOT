"""Closed-bar fractal swings — confirmable only after right-side bars exist (no look-ahead)."""

from __future__ import annotations

from typing import Any

from signal_bot.asia_london_mss.constants import SWING_LEFT, SWING_RIGHT


def confirmed_swing_highs(bars: list[dict[str, Any]], *, asof_idx: int) -> list[dict[str, Any]]:
    """Return swing highs whose confirmation bar index <= asof_idx."""
    out: list[dict[str, Any]] = []
    n = len(bars)
    L, R = SWING_LEFT, SWING_RIGHT
    # Candidate pivot i requires i+R <= asof_idx
    for i in range(L, n):
        confirm_idx = i + R
        if confirm_idx > asof_idx:
            break
        if confirm_idx >= n:
            break
        hi = float(bars[i]["high"])
        ok = True
        for j in range(i - L, i + R + 1):
            if j == i:
                continue
            if float(bars[j]["high"]) >= hi:
                ok = False
                break
        if ok:
            out.append(
                {
                    "kind": "SWING_HIGH",
                    "idx": i,
                    "confirm_idx": confirm_idx,
                    "price": hi,
                    "timestamp_utc": str(bars[i]["timestamp_utc"]),
                    "confirm_timestamp_utc": str(bars[confirm_idx]["timestamp_utc"]),
                }
            )
    return out


def confirmed_swing_lows(bars: list[dict[str, Any]], *, asof_idx: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = len(bars)
    L, R = SWING_LEFT, SWING_RIGHT
    for i in range(L, n):
        confirm_idx = i + R
        if confirm_idx > asof_idx:
            break
        if confirm_idx >= n:
            break
        lo = float(bars[i]["low"])
        ok = True
        for j in range(i - L, i + R + 1):
            if j == i:
                continue
            if float(bars[j]["low"]) <= lo:
                ok = False
                break
        if ok:
            out.append(
                {
                    "kind": "SWING_LOW",
                    "idx": i,
                    "confirm_idx": confirm_idx,
                    "price": lo,
                    "timestamp_utc": str(bars[i]["timestamp_utc"]),
                    "confirm_timestamp_utc": str(bars[confirm_idx]["timestamp_utc"]),
                }
            )
    return out


def last_confirmed_swing_high(bars: list[dict[str, Any]], *, asof_idx: int) -> dict[str, Any] | None:
    hs = confirmed_swing_highs(bars, asof_idx=asof_idx)
    return hs[-1] if hs else None


def last_confirmed_swing_low(bars: list[dict[str, Any]], *, asof_idx: int) -> dict[str, Any] | None:
    ls = confirmed_swing_lows(bars, asof_idx=asof_idx)
    return ls[-1] if ls else None
