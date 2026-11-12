"""Autonomous market observer — validate, feature, regime; never silent-fill."""

from __future__ import annotations

import uuid
from typing import Any

from phase49.atr import atr_at
from phase49.features import compute_features
from phase54.constants import ATR_PERIOD, FEATURE_VERSION, SYMBOL, TIMEFRAME
from phase54.timeutil import dual_stamp, now_utc_iso


def validate_bar(bar: dict[str, Any]) -> list[str]:
    errs = []
    for k in ("timestamp_utc", "open", "high", "low", "close"):
        if k not in bar or bar[k] is None:
            errs.append(f"missing:{k}")
    if errs:
        return errs
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    if not (h >= max(o, c) and l <= min(o, c)):
        errs.append("ohlc_inconsistent")
    if min(o, h, l, c) <= 0:
        errs.append("non_positive_price")
    return errs


def validate_tick_path(ticks_by_bar: dict[str, list], bar_ts: str) -> list[str]:
    ticks = ticks_by_bar.get(bar_ts) or []
    if not ticks:
        return ["missing_bid_ask_ticks"]
    for t in ticks:
        if t.get("bid") is None or t.get("ask") is None:
            return ["invalid_tick_ba"]
        if float(t["ask"]) < float(t["bid"]):
            return ["crossed_market"]
    return []


def detect_gaps(m5: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report unexpected >5m gaps between consecutive M5 opens (no fill)."""
    gaps = []
    for a, b in zip(m5, m5[1:]):
        ta, tb = str(a["timestamp_utc"]), str(b["timestamp_utc"])
        # lexical compare works for zero-padded timestamps; expect 5 minutes
        # If gap larger than 5 minutes wall, record (session breaks expected overnight)
        if ta[:10] == tb[:10]:
            ma = int(ta[11:13]) * 60 + int(ta[14:16])
            mb = int(tb[11:13]) * 60 + int(tb[14:16])
            if mb - ma > 5:
                gaps.append({"from": ta, "to": tb, "minutes": mb - ma})
    return gaps


def session_flags(ts: str) -> dict[str, Any]:
    hour = int(ts[11:13]) + int(ts[14:16]) / 60.0
    return {
        "london_active": 7 <= hour < 16,
        "ny_active": 12 <= hour < 21,
        "overlap": 12 <= hour < 16,
        "hour_utc": hour,
    }


def regime_from_features(feats: dict[str, float | None]) -> dict[str, Any]:
    rv = feats.get("C02_rv_48")
    accel = feats.get("C03_vol_accel")
    disp = feats.get("B02_net_disp_atr_12")
    if rv is None:
        label = "UNKNOWN"
    elif accel is not None and accel > 1.5:
        label = "HIGH_VOL_ACCEL"
    elif disp is not None and abs(float(disp)) >= 0.5:
        label = "DISPLACED"
    else:
        label = "QUIET_OR_CHOP"
    return {
        "label": label,
        "rv_48": rv,
        "vol_accel": accel,
        "net_disp_atr_12": disp,
        "spread_atr": feats.get("E02_spread_atr"),
        "overlap": feats.get("D03_overlap"),
    }


def build_observation(
    *,
    m5: list[dict[str, Any]],
    idx: int,
    h1: list[dict[str, Any]],
    ticks_by_bar: dict[str, list],
    day: str,
) -> dict[str, Any]:
    obs_id = uuid.uuid4().hex
    stamp = now_utc_iso()
    if idx < 0 or idx >= len(m5):
        return {
            "observation_id": obs_id,
            "accepted": False,
            "data_quality_status": "INVALID_INDEX",
            "errors": ["index_oob"],
            "created_iso": stamp,
        }

    bar = m5[idx]
    bar_ts = str(bar["timestamp_utc"])
    errors = validate_bar(bar)
    errors.extend(validate_tick_path(ticks_by_bar, bar_ts))

    # Require lookback for features
    if idx < 48:
        errors.append("insufficient_lookback")

    if errors:
        return {
            "observation_id": obs_id,
            "accepted": False,
            "data_quality_status": "REJECTED",
            "errors": errors,
            "day": day,
            "bar_timestamp_utc": bar_ts,
            "timestamps": dual_stamp(bar_ts),
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "created_iso": stamp,
        }

    feats = compute_features(m5=m5, idx=idx, h1=h1, ticks_by_bar=ticks_by_bar, prior_day_range=None)
    atr = atr_at(m5, idx, ATR_PERIOD)
    last_ticks = ticks_by_bar.get(bar_ts) or []
    last = last_ticks[-1]
    spread = float(last["ask"]) - float(last["bid"])
    regime = regime_from_features(feats)
    gaps = detect_gaps(m5[: idx + 1])

    return {
        "observation_id": obs_id,
        "accepted": True,
        "data_quality_status": "OK",
        "errors": [],
        "day": day,
        "decision_idx": idx,
        "bar_timestamp_utc": bar_ts,
        "timestamps": dual_stamp(bar_ts),
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "features": feats,
        "feature_version": FEATURE_VERSION,
        "atr": atr,
        "bid": float(last["bid"]),
        "ask": float(last["ask"]),
        "spread": spread,
        "session": session_flags(bar_ts),
        "regime": regime,
        "intraday_gaps_n": len(gaps),
        "gaps_sample": gaps[-3:],
        "created_iso": stamp,
        "market_state_id": f"{SYMBOL}:{TIMEFRAME}:{bar_ts}",
    }
