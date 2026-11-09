"""Audit independent M5 bars. Do not repair, fill, interpolate, or drop silently."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np

from phase5.constants import (
    APPROVED_M5_START,
    BAR_MINUTES,
    INDEPENDENT_RAW,
    POINT_SIZE,
    RESEARCH_CUTOFF,
    SERVER_TZ,
    TIME_FORMAT,
)


def load_raw(path=INDEPENDENT_RAW) -> list[dict]:
    import csv
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for rec in rows:
        out.append({
            "time": rec["time"],
            "open": float(rec["open"]),
            "high": float(rec["high"]),
            "low": float(rec["low"]),
            "close": float(rec["close"]),
            "tick_volume": float(rec["tick_volume"]),
            "spread": float(rec["spread"]),
        })
    return out


def audit_raw(rows: list[dict]) -> dict:
    issues = []
    n = len(rows)
    if n == 0:
        return {"passed": False, "status": "empty", "issues": ["no rows"]}
    times = [r["time"] for r in rows]
    dts = [datetime.strptime(t, TIME_FORMAT) for t in times]
    earliest, latest = times[0], times[-1]
    if latest >= APPROVED_M5_START:
        issues.append("latest timestamp is not strictly before approved M5 start")
    if latest >= RESEARCH_CUTOFF:
        issues.append("latest timestamp exceeds research cutoff")
    if earliest >= APPROVED_M5_START:
        issues.append("earliest timestamp is not before approved M5 start")
    dups = n - len(set(times))
    if dups:
        issues.append(f"duplicate timestamps: {dups}")
    backwards = sum(1 for i in range(1, n) if dts[i] <= dts[i - 1])
    if backwards:
        issues.append(f"non-increasing timestamps: {backwards}")

    step = timedelta(minutes=BAR_MINUTES)
    gaps_gt_5 = 0
    weekendish = 0
    suspicious = 0
    gap_minutes = []
    for i in range(1, n):
        delta = dts[i] - dts[i - 1]
        mins = delta.total_seconds() / 60.0
        if mins > BAR_MINUTES:
            gaps_gt_5 += 1
            gap_minutes.append(mins)
            if mins > 12 * 60:
                weekendish += 1
            # Weekday gap longer than 1 hour and not a typical daily ~5-7h gold break
            if mins > 8 * 60 and dts[i].weekday() < 5 and dts[i - 1].weekday() < 5:
                suspicious += 1

    ohlc_bad = 0
    zero_range = 0
    neg_vol = 0
    not_point = 0
    for r in rows:
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        if not (h >= max(o, c) and l <= min(o, c) and h >= l):
            ohlc_bad += 1
        if h - l <= 0:
            zero_range += 1
        if r["tick_volume"] < 0:
            neg_vol += 1
        px = np.array([o, h, l, c])
        if np.any(np.abs(px / POINT_SIZE - np.round(px / POINT_SIZE)) > 1e-6):
            not_point += 1
    if ohlc_bad:
        issues.append(f"invalid OHLC: {ohlc_bad}")
    if neg_vol:
        issues.append(f"negative tick_volume: {neg_vol}")

    dst_bad = 0
    try:
        athens = ZoneInfo(SERVER_TZ)
        for t in dts:
            loc = t.replace(tzinfo=athens)
            if loc is None:
                dst_bad += 1
    except ZoneInfoNotFoundError:
        issues.append("tzdata/IANA zone Europe/Athens unavailable")

    material = bool(issues) or ohlc_bad > 0 or backwards > 0 or dups > 0 or latest >= APPROVED_M5_START
    return {
        "passed": not material,
        "material_quality_problem": material,
        "n": n,
        "earliest": earliest,
        "latest": latest,
        "duplicate_timestamps": dups,
        "backwards_or_ties": backwards,
        "gaps_gt_5min": gaps_gt_5,
        "gaps_gt_12h": weekendish,
        "suspicious_weekday_gaps_gt_8h": suspicious,
        "median_gap_minutes_when_gt_5": float(np.median(gap_minutes)) if gap_minutes else None,
        "ohlc_invalid": ohlc_bad,
        "zero_or_negative_range": zero_range,
        "negative_volume": neg_vol,
        "not_point_size_multiples": not_point,
        "dst_unlocalizable": dst_bad,
        "timezone_interpretation": (
            "Naive stamps are treated as Europe/Athens wall clock, then converted to UTC "
            "(same methodology as Phase 1 UTC correction). Not treated as true UTC."
        ),
        "issues": issues,
        "note": "Gaps are expected around weekends/daily gold breaks and are not filled.",
    }
