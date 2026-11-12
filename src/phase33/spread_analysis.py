"""Historical spread distribution from verified bid/ask ticks."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from phase33.constants import (
    MIN_SPREAD_POINTS,
    POINT_SIZE,
    SESSION_WINDOWS_UTC,
)
from phase33.progress import write_json


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if p <= 0:
        return sorted_vals[0]
    if p >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _stats(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    mean = sum(s) / len(s)
    return {
        "n": len(s),
        "mean": mean,
        "median": _percentile(s, 50),
        "p25": _percentile(s, 25),
        "p75": _percentile(s, 75),
        "p90": _percentile(s, 90),
        "p95": _percentile(s, 95),
        "p99": _percentile(s, 99),
        "max": s[-1],
        "min": s[0],
    }


def _session_for_hour(hour: int) -> list[str]:
    tags = []
    for name, (lo, hi) in SESSION_WINDOWS_UTC.items():
        if lo <= hour < hi:
            tags.append(name)
    return tags or ["other"]


def analyze_spreads(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    if not ticks:
        report = {"pass": False, "reason": "no_ticks"}
        write_json("spread_analysis.json", report)
        return report

    spreads_usd = [float(t["ask"]) - float(t["bid"]) for t in ticks]
    # Flag any inconsistency with stored spread field
    mismatch = sum(
        1 for t, s in zip(ticks, spreads_usd) if abs(float(t["spread"]) - s) > 1e-12
    )
    spreads_points = [s / POINT_SIZE for s in spreads_usd]

    by_session: dict[str, list[float]] = defaultdict(list)
    by_hour: dict[str, list[float]] = defaultdict(list)
    by_weekday: dict[str, list[float]] = defaultdict(list)

    for t, s in zip(ticks, spreads_usd):
        dt = datetime.strptime(t["timestamp_utc"], "%Y-%m-%d %H:%M:%S")
        for tag in _session_for_hour(dt.hour):
            by_session[tag].append(s)
        by_hour[f"{dt.hour:02d}"].append(s)
        by_weekday[dt.strftime("%A")].append(s)

    # Volatility regime proxy: per-M5 realized range of mid using tick groups is heavy;
    # use hour-level stdev of mid returns as coarse regime labels.
    hour_mids: dict[str, list[float]] = defaultdict(list)
    for t in ticks:
        key = t["timestamp_utc"][:13]  # YYYY-MM-DD HH
        hour_mids[key].append(float(t["mid"]))
    hour_vol = {}
    for key, mids in hour_mids.items():
        if len(mids) < 2:
            hour_vol[key] = 0.0
        else:
            rets = [mids[i] - mids[i - 1] for i in range(1, len(mids))]
            mu = sum(rets) / len(rets)
            var = sum((r - mu) ** 2 for r in rets) / max(len(rets) - 1, 1)
            hour_vol[key] = math.sqrt(var)
    vol_vals = sorted(hour_vol.values())
    if vol_vals:
        p33 = _percentile(vol_vals, 33)
        p66 = _percentile(vol_vals, 66)
    else:
        p33 = p66 = 0.0
    by_vol_regime: dict[str, list[float]] = defaultdict(list)
    for t, s in zip(ticks, spreads_usd):
        key = t["timestamp_utc"][:13]
        v = hour_vol.get(key, 0.0)
        regime = "low" if v <= p33 else ("high" if v >= p66 else "mid")
        by_vol_regime[regime].append(s)

    # Outliers: > p99 flagged, not deleted
    p99 = _percentile(sorted(spreads_usd), 99)
    outliers = [
        {
            "timestamp_utc": t["timestamp_utc"],
            "spread_usd": float(t["ask"]) - float(t["bid"]),
            "bid": float(t["bid"]),
            "ask": float(t["ask"]),
        }
        for t in ticks
        if (float(t["ask"]) - float(t["bid"])) > p99
    ]

    frozen_floor_usd = MIN_SPREAD_POINTS * POINT_SIZE
    frac_below_floor = sum(1 for s in spreads_usd if s < frozen_floor_usd) / len(spreads_usd)
    frac_above_floor = 1.0 - frac_below_floor

    report = {
        "n_ticks": len(ticks),
        "spread_definition": "ask - bid",
        "units": {
            "absolute_usd": True,
            "project_price_points": True,
            "point_size_usd": POINT_SIZE,
        },
        "overall_usd": _stats(spreads_usd),
        "overall_points": _stats(spreads_points),
        "by_session_usd": {k: _stats(v) for k, v in sorted(by_session.items())},
        "by_hour_usd": {k: _stats(v) for k, v in sorted(by_hour.items())},
        "by_weekday_usd": {k: _stats(v) for k, v in sorted(by_weekday.items())},
        "by_volatility_regime_usd": {k: _stats(v) for k, v in sorted(by_vol_regime.items())},
        "outliers_above_p99": {
            "p99_usd": p99,
            "n_flagged": len(outliers),
            "deleted": False,
            "sample": outliers[:50],
        },
        "vs_frozen_spread_floor": {
            "floor_points": MIN_SPREAD_POINTS,
            "floor_usd": frozen_floor_usd,
            "fraction_ticks_below_floor": frac_below_floor,
            "fraction_ticks_at_or_above_floor": frac_above_floor,
            "note": "Single average spread is NOT a substitute for this distribution.",
        },
        "stored_spread_field_mismatches": mismatch,
        "market_closure_notes": [
            "Empty bi5 hours (weekend / daily break) produce no ticks — not fabricated.",
            "Large inter-tick gaps may reflect session breaks; spreads during reopen can spike.",
        ],
        "pass": mismatch == 0 and len(spreads_usd) > 0,
    }
    write_json("spread_analysis.json", report)
    return report
