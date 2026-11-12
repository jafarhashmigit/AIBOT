"""Phase58 feature family — only new, non-revived signals available at decision time."""

from __future__ import annotations

from typing import Any

from phase49.atr import atr_at
from phase58.constants import ATR_PERIOD


def mid_from_ticks(ticks: list[dict[str, Any]] | None) -> float | None:
    if not ticks:
        return None
    t = ticks[0]
    return (float(t["bid"]) + float(t["ask"])) / 2.0


def compute_phase58_features(
    *,
    m5: list[dict[str, Any]],
    idx: int,
    ticks_by_bar: dict[str, list],
    prior_session_m5: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    bar = m5[idx]
    ts = str(bar["timestamp_utc"])
    ticks = ticks_by_bar.get(ts) or []
    atr = atr_at(m5, idx, ATR_PERIOD)
    spread = None
    if ticks:
        spread = float(ticks[0]["ask"]) - float(ticks[0]["bid"])
    spread_atr = (spread / atr) if (spread is not None and atr and atr > 0) else None

    # 1-bar mid return using completed bars only (idx-1 → idx)
    ret_1 = None
    if idx >= 1:
        m0 = mid_from_ticks(ticks_by_bar.get(str(m5[idx - 1]["timestamp_utc"])))
        m1 = mid_from_ticks(ticks)
        if m0 and m1 and m0 > 0:
            ret_1 = (m1 - m0) / m0

    tick_vol = float(bar.get("tick_volume") or 0)

    # Prior archived session range location of current mid
    prior_loc = None
    prior_range = None
    if prior_session_m5:
        highs = [float(b["high"]) for b in prior_session_m5]
        lows = [float(b["low"]) for b in prior_session_m5]
        if highs and lows:
            hi, lo = max(highs), min(lows)
            prior_range = hi - lo
            mid = mid_from_ticks(ticks)
            if mid is not None and prior_range and prior_range > 0:
                prior_loc = (mid - lo) / prior_range

    hour = int(ts[11:13]) if len(ts) >= 13 else None

    return {
        "spread": spread,
        "atr": atr,
        "spread_atr": spread_atr,
        "ret_1bar_mid": ret_1,
        "tick_volume": tick_vol,
        "prior_session_range": prior_range,
        "prior_session_location": prior_loc,
        "hour_utc": hour,
        "bar_timestamp_utc": ts,
        "feature_family_version": "phase58_v1",
    }
