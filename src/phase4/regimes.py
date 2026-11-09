"""Assign predeclared regime labels. Tercile cuts come from inner data only."""

from __future__ import annotations

import numpy as np

from phase4.constants import HOUR_BUCKETS, SESSION_NAMES, WEEKDAY_NAMES


def hour_bucket(hour: int) -> str:
    for name, hours in HOUR_BUCKETS:
        if hour in hours:
            return name
    return "utc_other"


def session_name(session_id: int) -> str:
    return SESSION_NAMES.get(int(session_id), "unknown")


def weekday_name(wd: int) -> str:
    return WEEKDAY_NAMES.get(int(wd), "weekend")


def tercile_cuts(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if len(finite) < 10:
        raise RuntimeError("not enough inner rows to form atr terciles")
    lo, hi = np.quantile(finite, [1.0 / 3.0, 2.0 / 3.0])
    return float(lo), float(hi)


def assign_tercile(value: float, lo: float, hi: float) -> str:
    if value <= lo:
        return "low"
    if value <= hi:
        return "mid"
    return "high"


def attach_regimes(rows: list[dict], atr_cuts: tuple[float, float] | None) -> list[dict]:
    out = []
    for row in rows:
        item = dict(row)
        item["regime_session"] = session_name(row["corrected_session_id"])
        item["regime_hour"] = hour_bucket(int(row["corrected_hour_utc"]))
        item["regime_weekday"] = weekday_name(int(row["corrected_weekday_utc"]))
        item["regime_trend"] = "ema_up" if row["ema_9_20_spread"] > 0 else "ema_down"
        if atr_cuts is None:
            item["regime_atr"] = "unassigned"
        else:
            item["regime_atr"] = assign_tercile(row["atr_14_pct"], atr_cuts[0], atr_cuts[1])
        out.append(item)
    return out
