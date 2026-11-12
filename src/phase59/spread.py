"""Observed bid/ask spread intelligence — never invent spreads."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from phase49.atr import atr_at
from phase54.constants import SYMBOL
from phase59.constants import ATR_PERIOD, SESSION_WINDOWS, canonical_json_sha256
from phase59.inventory import load_jsonl, resolve_root_for_day
from phase59.tick_stream import scan_day_ticks


def _session(hour: int) -> str:
    for name, (a, b) in SESSION_WINDOWS.items():
        if a <= hour < b:
            return name
    return "OFF_HOURS"


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(p * (len(ys) - 1))))
    return ys[i]


def _summarize(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
            "std": None,
        }
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return {
        "n": len(xs),
        "mean": m,
        "median": _percentile(xs, 0.5),
        "p75": _percentile(xs, 0.75),
        "p90": _percentile(xs, 0.9),
        "p95": _percentile(xs, 0.95),
        "p99": _percentile(xs, 0.99),
        "max": max(xs),
        "std": var ** 0.5,
    }


def collect_spreads(days: list[str]) -> dict[str, Any]:
    by_session: dict[str, list[float]] = defaultdict(list)
    by_weekday: dict[str, list[float]] = defaultdict(list)
    by_hour: dict[int, list[float]] = defaultdict(list)
    all_spreads: list[float] = []
    spread_atr: list[float] = []
    unobservable_bars = 0
    observable_bars = 0
    expansion_events = 0
    persistence_hits = 0
    persistence_trials = 0

    for day in days:
        root = resolve_root_for_day(day)
        if root is None:
            continue
        m5 = load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
        spreads = scan_day_ticks(root, day)["spreads"]
        try:
            weekday = datetime.strptime(day, "%Y-%m-%d").strftime("%A")
        except Exception:
            weekday = "UNK"

        prev_spread = None
        prev_wide = False
        day_spreads: list[float] = []
        for i, bar in enumerate(m5):
            ts = str(bar["timestamp_utc"])
            hour = int(ts[11:13]) if len(ts) >= 13 else 0
            sp = spreads.get(ts)
            if sp is None:
                unobservable_bars += 1
                prev_spread = None
                prev_wide = False
                continue
            observable_bars += 1
            all_spreads.append(sp)
            day_spreads.append(sp)
            by_session[_session(hour)].append(sp)
            by_weekday[weekday].append(sp)
            by_hour[hour].append(sp)
            atr = atr_at(m5, i, ATR_PERIOD)
            if atr and atr > 0:
                spread_atr.append(sp / atr)
            if prev_spread is not None and prev_spread > 0 and sp > 2.0 * prev_spread:
                expansion_events += 1
            if prev_wide:
                persistence_trials += 1
                if sp >= (prev_spread or 0):
                    persistence_hits += 1
            prev_spread = sp
            med = sorted(day_spreads)[len(day_spreads) // 2]
            prev_wide = sp > med

    overlap = []
    for h in range(12, 16):
        overlap.extend(by_hour.get(h) or [])

    report = {
        "definition": "Observed first-tick bid/ask spread per M5 bar; not assumed broker schedule",
        "overall": _summarize(all_spreads),
        "spread_over_atr": _summarize(spread_atr),
        "by_session": {k: _summarize(v) for k, v in sorted(by_session.items())},
        "by_weekday": {k: _summarize(v) for k, v in sorted(by_weekday.items())},
        "by_hour_utc": {str(k): _summarize(v) for k, v in sorted(by_hour.items())},
        "london_ny_overlap_12_16_utc": _summarize(overlap),
        "observable_bars": observable_bars,
        "unobservable_bars_no_ticks": unobservable_bars,
        "spread_expansion_events_gt_2x_prev": expansion_events,
        "spread_persistence_rate": (persistence_hits / persistence_trials) if persistence_trials else None,
        "persistence_trials": persistence_trials,
        "assumed_spread": None,
        "note": "Periods without ticks are insufficiently observable — not treated as zero spread",
        "n_days": len(days),
    }
    report["spread_sha256"] = canonical_json_sha256({k: v for k, v in report.items() if k != "spread_sha256"})
    return report
