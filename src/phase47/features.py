"""Causal features at decision bar — completed M5 only, no forming future bars."""

from __future__ import annotations

import math
from typing import Any

from phase46.atr import atr_at_bar
from phase47.constants import ATR_PERIOD, FEATURE_NAMES, HORIZON_BARS


def _close(m5: list[dict[str, Any]], i: int) -> float:
    return float(m5[i]["close"])


def build_feature_vector(m5: list[dict[str, Any]], idx: int) -> dict[str, float] | None:
    """Features using bars <= idx only. Requires idx >= max(12, ATR_PERIOD)."""
    need = max(12, ATR_PERIOD)
    if idx < need or idx >= len(m5):
        return None
    c = _close(m5, idx)
    if c <= 0:
        return None

    def ret(n: int) -> float:
        return (_close(m5, idx) / _close(m5, idx - n)) - 1.0

    atr = atr_at_bar(m5, idx, ATR_PERIOD)
    if atr is None or atr <= 0:
        return None
    high = float(m5[idx]["high"])
    low = float(m5[idx]["low"])
    open_ = float(m5[idx]["open"])
    rng = high - low
    range_pct = rng / c
    body_pct = abs(c - open_) / c
    close_loc = 0.5 if rng <= 0 else (c - low) / rng

    ranges = [(float(m5[j]["high"]) - float(m5[j]["low"])) / max(_close(m5, j), 1e-12) for j in range(idx - 11, idx + 1)]
    mean_r = sum(ranges) / len(ranges)
    range_compression = range_pct / mean_r if mean_r > 0 else 1.0
    # realized vol of 1-bar returns
    rets = [(_close(m5, j) / _close(m5, j - 1)) - 1.0 for j in range(idx - 11, idx + 1)]
    mu = sum(rets) / len(rets)
    realized_vol_12 = math.sqrt(sum((x - mu) ** 2 for x in rets) / len(rets))

    ts = str(m5[idx]["timestamp_utc"])
    hour = int(ts[11:13]) + int(ts[14:16]) / 60.0
    hour_sin = math.sin(2 * math.pi * hour / 24.0)
    hour_cos = math.cos(2 * math.pi * hour / 24.0)

    spread_raw = m5[idx].get("spread")
    # MT5 spread often in points; treat as relative proxy only if present
    if spread_raw is None:
        spread_pct = 0.0
    else:
        spread_pct = float(spread_raw) * 0.01 / c  # points→price heuristic for XAU; documented as proxy

    feats = {
        "ret_1": ret(1),
        "ret_3": ret(3),
        "ret_6": ret(6),
        "ret_12": ret(12),
        "atr_pct": atr / c,
        "range_pct": range_pct,
        "body_pct": body_pct,
        "close_loc": close_loc,
        "range_compression": range_compression,
        "hour_sin": hour_sin,
        "hour_cos": hour_cos,
        "spread_pct": spread_pct,
        "realized_vol_12": realized_vol_12,
    }
    assert list(feats.keys()) == FEATURE_NAMES or set(feats.keys()) == set(FEATURE_NAMES)
    return feats


def attach_features_to_outcomes(
    outcomes: list[dict[str, Any]],
    m5_by_day: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Join causal features onto BUY/SELL rows; skip if feature unavailable."""
    out: list[dict[str, Any]] = []
    for r in outcomes:
        if r.get("action") not in ("BUY", "SELL"):
            continue
        if r.get("data_quality_status") != "OK":
            continue
        day = str(r["day"])
        m5 = m5_by_day[day]
        idx_map = {str(b["timestamp_utc"]): i for i, b in enumerate(m5)}
        idx = idx_map.get(str(r["decision_bar"]))
        if idx is None:
            continue
        # Leakage guard: entry is idx+1; features must not use entry/exit bars
        if idx + 1 + HORIZON_BARS - 1 >= len(m5):
            continue
        feats = build_feature_vector(m5, idx)
        if feats is None:
            continue
        row = dict(r)
        row["features"] = feats
        row["feature_names"] = list(FEATURE_NAMES)
        row["decision_idx"] = idx
        out.append(row)
    return out


def matrix_xy(rows: list[dict[str, Any]]) -> tuple[list[list[float]], list[float], list[int]]:
    X: list[list[float]] = []
    y: list[float] = []
    pos: list[int] = []
    for i, r in enumerate(rows):
        feats = r["features"]
        X.append([float(feats[n]) for n in FEATURE_NAMES])
        y.append(float(r["net_r"]))
        pos.append(1 if float(r["net_r"]) > 0 else 0)
    return X, y, pos
