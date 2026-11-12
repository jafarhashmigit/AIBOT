"""Extended spread distribution vs Phase 33 reference."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from phase34.constants import (
    PHASE33_SPREAD_REF,
    POINT_SIZE,
    POINTS_THRESHOLDS,
    SESSION_WINDOWS_UTC,
)
from phase34.progress import write_json


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
    return {
        "n": len(s),
        "min": s[0],
        "max": s[-1],
        "mean": sum(s) / len(s),
        "median": _percentile(s, 50),
        "p50": _percentile(s, 50),
        "p75": _percentile(s, 75),
        "p90": _percentile(s, 90),
        "p95": _percentile(s, 95),
        "p99": _percentile(s, 99),
    }


def _sessions(hour: int) -> list[str]:
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
    spreads_pts = [s / POINT_SIZE for s in spreads_usd]

    by_month: dict[str, list[float]] = defaultdict(list)
    by_weekday: dict[str, list[float]] = defaultdict(list)
    by_hour: dict[str, list[float]] = defaultdict(list)
    by_session: dict[str, list[float]] = defaultdict(list)

    for t, s in zip(ticks, spreads_usd):
        dt = datetime.strptime(t["timestamp_utc"], "%Y-%m-%d %H:%M:%S")
        by_month[dt.strftime("%Y-%m")].append(s)
        by_weekday[dt.strftime("%A")].append(s)
        by_hour[f"{dt.hour:02d}"].append(s)
        for tag in _sessions(dt.hour):
            by_session[tag].append(s)

    pct_above = {}
    for thr in POINTS_THRESHOLDS:
        usd_thr = thr * POINT_SIZE
        pct_above[str(thr)] = sum(1 for s in spreads_usd if s > usd_thr) / len(spreads_usd)

    overall = _stats(spreads_usd)
    overall_pts = _stats(spreads_pts)

    # Compare to Phase 33
    ref = PHASE33_SPREAD_REF
    cmp = {
        "phase33_ref": ref,
        "phase34_median_usd": overall.get("median"),
        "phase34_mean_usd": overall.get("mean"),
        "phase34_p95_usd": overall.get("p95"),
        "delta_median_usd": (overall.get("median") or 0) - ref["median_usd"],
        "delta_mean_usd": (overall.get("mean") or 0) - ref["mean_usd"],
        "delta_p95_usd": (overall.get("p95") or 0) - ref["p95_usd"],
    }
    # Representativeness heuristic: |delta median| < $0.15 and |delta p95| < $0.30
    med_ok = abs(cmp["delta_median_usd"]) < 0.15
    p95_ok = abs(cmp["delta_p95_usd"]) < 0.30
    if med_ok and p95_ok:
        representativeness = "PHASE33_SAMPLE_APPEARS_REPRESENTATIVE"
    else:
        representativeness = "PHASE33_SAMPLE_MATERIALLY_DIFFERENT"

    report = {
        "n_ticks": len(ticks),
        "point_size_usd": POINT_SIZE,
        "spread_definition": "ask - bid",
        "overall_usd": overall,
        "overall_points": overall_pts,
        "by_month_usd": {k: _stats(v) for k, v in sorted(by_month.items())},
        "by_weekday_usd": {k: _stats(v) for k, v in sorted(by_weekday.items())},
        "by_hour_utc_usd": {k: _stats(v) for k, v in sorted(by_hour.items())},
        "by_session_usd": {k: _stats(v) for k, v in sorted(by_session.items())},
        "pct_observations_above_points": pct_above,
        "phase33_comparison": cmp,
        "representativeness": representativeness,
        "pass": True,
    }
    write_json("spread_analysis.json", report)
    return report


def independent_recompute_from_jsonl(paths: list[Any]) -> dict[str, Any]:
    """Recompute spread summary from saved tick JSONL files (no download)."""
    import json
    from pathlib import Path

    ticks = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    spreads = [float(t["ask"]) - float(t["bid"]) for t in ticks]
    if not spreads:
        return {"n": 0}
    s = sorted(spreads)
    return {
        "n": len(s),
        "median": _percentile(s, 50),
        "mean": sum(s) / len(s),
        "p95": _percentile(s, 95),
        "min": s[0],
        "max": s[-1],
    }
