"""Shared day scan cache so integrity + spread share one tick pass per day."""

from __future__ import annotations

from collections import Counter, defaultdict
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
    return ys[min(len(ys) - 1, max(0, int(p * (len(ys) - 1))))]


def _summarize(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0, "mean": None, "median": None, "p75": None, "p90": None, "p95": None, "p99": None, "max": None, "std": None}
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


def _ohlc_errors(bar: dict[str, Any]) -> list[str]:
    try:
        o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    except Exception:
        return ["non_numeric_ohlc"]
    errs = []
    for name, v in (("open", o), ("high", h), ("low", l), ("close", c)):
        if v <= 0:
            errs.append(f"non_positive_{name}")
    if h < l:
        errs.append("high_lt_low")
    if h < max(o, c) or l > min(o, c):
        errs.append("ohlc_inconsistent")
    return errs


def scan_days(days: list[str]) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for day in days:
        root = resolve_root_for_day(day)
        if root is None:
            cache[day] = {"missing": True}
            continue
        m5 = load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
        h1 = load_jsonl(root / "h1" / f"h1_{SYMBOL}_{day}_warmup.jsonl")
        scanned = scan_day_ticks(root, day)
        cache[day] = {
            "missing": False,
            "root": str(root),
            "m5": m5,
            "h1_n": len(h1),
            "scanned": scanned,
        }
    return cache


def integrity_from_cache(cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for day, c in cache.items():
        if c.get("missing"):
            rows.append({"day": day, "ok": False, "excluded_reason": "missing_archive"})
            continue
        m5 = c["m5"]
        scanned = c["scanned"]
        spreads = scanned["spreads"]
        ts_list = [str(b.get("timestamp_utc")) for b in m5]
        dup_ts = [t for t, n in Counter(ts_list).items() if n > 1]
        ohlc_bad = [{"idx": i, "ts": b.get("timestamp_utc"), "errors": e} for i, b in enumerate(m5) if (e := _ohlc_errors(b))]
        gaps = []
        for a, b in zip(m5, m5[1:]):
            ta, tb = str(a["timestamp_utc"]), str(b["timestamp_utc"])
            try:
                da = datetime.strptime(ta[:19], "%Y-%m-%d %H:%M:%S")
                db = datetime.strptime(tb[:19], "%Y-%m-%d %H:%M:%S")
                delta = (db - da).total_seconds() / 60.0
                if delta > 5.5:
                    gaps.append({"from": ta, "to": tb, "gap_minutes": delta})
            except Exception:
                gaps.append({"from": ta, "to": tb, "gap_minutes": None, "parse_error": True})
        bars_without = [str(b["timestamp_utc"]) for b in m5 if str(b["timestamp_utc"]) not in spreads]
        excluded = []
        if dup_ts:
            excluded.append({"reason": "duplicate_timestamps", "n": len(dup_ts)})
        if ohlc_bad:
            excluded.append({"reason": "invalid_ohlc", "n": len(ohlc_bad)})
        rows.append(
            {
                "day": day,
                "source_root": c["root"],
                "m5_n": len(m5),
                "h1_n": c["h1_n"],
                "ticks_n": scanned["ticks_n"],
                "tick_hours_present": scanned["tick_hours_present"],
                "n_duplicate_timestamps": len(dup_ts),
                "duplicate_timestamps_sample": dup_ts[:5],
                "n_ohlc_errors": len(ohlc_bad),
                "ohlc_errors_sample": ohlc_bad[:5],
                "n_gaps_gt_5m": len(gaps),
                "gaps_sample": gaps[:10],
                "ticks_missing_bidask": scanned["missing_ba"],
                "ticks_crossed": scanned["crossed"],
                "bars_without_ticks_n": len(bars_without),
                "bars_without_ticks_sample": bars_without[:5],
                "bidask_observable": scanned["ticks_n"] > 0,
                "excluded_observations": excluded,
                "ok": len(dup_ts) == 0 and len(ohlc_bad) == 0 and scanned["crossed"] == 0,
            }
        )
    summary = {
        "n_days": len(rows),
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "n_dup_ts_days": sum(1 for r in rows if r.get("n_duplicate_timestamps", 0) > 0),
        "n_ohlc_error_days": sum(1 for r in rows if r.get("n_ohlc_errors", 0) > 0),
        "n_gap_days": sum(1 for r in rows if r.get("n_gaps_gt_5m", 0) > 0),
        "total_m5_bars": sum(int(r.get("m5_n") or 0) for r in rows),
        "total_ticks": sum(int(r.get("ticks_n") or 0) for r in rows),
        "days_without_ticks": [r["day"] for r in rows if int(r.get("ticks_n") or 0) == 0],
        "days_with_bars_missing_ticks": [r["day"] for r in rows if int(r.get("bars_without_ticks_n") or 0) > 0],
        "rows": rows,
    }
    summary["integrity_sha256"] = canonical_json_sha256(
        {k: v for k, v in summary.items() if k not in ("rows", "integrity_sha256")}
    )
    return summary


def spread_from_cache(cache: dict[str, dict[str, Any]], days: list[str]) -> dict[str, Any]:
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
        c = cache.get(day) or {}
        if c.get("missing"):
            continue
        m5 = c["m5"]
        spreads = c["scanned"]["spreads"]
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
