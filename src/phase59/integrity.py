"""Dataset integrity — report issues; never silently repair source data."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from phase54.constants import SYMBOL
from phase59.constants import canonical_json_sha256
from phase59.inventory import load_jsonl, resolve_root_for_day
from phase59.tick_stream import scan_day_ticks


def _ohlc_errors(bar: dict[str, Any]) -> list[str]:
    errs = []
    try:
        o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    except Exception:
        return ["non_numeric_ohlc"]
    for name, v in (("open", o), ("high", h), ("low", l), ("close", c)):
        if v <= 0:
            errs.append(f"non_positive_{name}")
    if h < l:
        errs.append("high_lt_low")
    if h < max(o, c) or l > min(o, c):
        errs.append("ohlc_inconsistent")
    return errs


def audit_day(day: str) -> dict[str, Any]:
    root = resolve_root_for_day(day)
    if root is None:
        return {"day": day, "ok": False, "excluded_reason": "missing_archive"}
    m5 = load_jsonl(root / "m5" / f"m5_{SYMBOL}_{day}.jsonl")
    h1 = load_jsonl(root / "h1" / f"h1_{SYMBOL}_{day}_warmup.jsonl")
    scanned = scan_day_ticks(root, day)
    spreads = scanned["spreads"]
    tstats = {
        "ticks_n": scanned["ticks_n"],
        "tick_hours_present": scanned["tick_hours_present"],
        "missing_ba": scanned["missing_ba"],
        "crossed": scanned["crossed"],
    }

    ts_list = [str(b.get("timestamp_utc")) for b in m5]
    dup_ts = [t for t, n in Counter(ts_list).items() if n > 1]
    ohlc_bad = []
    for i, b in enumerate(m5):
        e = _ohlc_errors(b)
        if e:
            ohlc_bad.append({"idx": i, "ts": b.get("timestamp_utc"), "errors": e})

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

    bars_without_ticks = [str(b["timestamp_utc"]) for b in m5 if str(b["timestamp_utc"]) not in spreads]
    excluded = []
    if dup_ts:
        excluded.append({"reason": "duplicate_timestamps", "n": len(dup_ts)})
    if ohlc_bad:
        excluded.append({"reason": "invalid_ohlc", "n": len(ohlc_bad)})

    return {
        "day": day,
        "source_root": str(root),
        "m5_n": len(m5),
        "h1_n": len(h1),
        "ticks_n": tstats["ticks_n"],
        "tick_hours_present": tstats["tick_hours_present"],
        "n_duplicate_timestamps": len(dup_ts),
        "duplicate_timestamps_sample": dup_ts[:5],
        "n_ohlc_errors": len(ohlc_bad),
        "ohlc_errors_sample": ohlc_bad[:5],
        "n_gaps_gt_5m": len(gaps),
        "gaps_sample": gaps[:10],
        "ticks_missing_bidask": tstats["missing_ba"],
        "ticks_crossed": tstats["crossed"],
        "bars_without_ticks_n": len(bars_without_ticks),
        "bars_without_ticks_sample": bars_without_ticks[:5],
        "bidask_observable": tstats["ticks_n"] > 0 and tstats["missing_ba"] == 0,
        "excluded_observations": excluded,
        "ok": len(dup_ts) == 0 and len(ohlc_bad) == 0 and tstats["crossed"] == 0,
    }


def audit_all_days(days: list[str]) -> dict[str, Any]:
    rows = [audit_day(d) for d in days]
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
