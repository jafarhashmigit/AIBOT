"""Load Phase40 full-session M5 / H1 / ticks (read-only)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from phase41.constants import (
    HORIZON_BARS,
    PHASE40_RAW_H1,
    PHASE40_RAW_M5,
    PHASE40_RAW_TICKS,
    SYMBOL,
    TARGET_DATES,
    TICK_HOURS,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def load_ticks_day(day: str) -> list[dict[str, Any]]:
    ticks: list[dict[str, Any]] = []
    for hour in TICK_HOURS:
        path = PHASE40_RAW_TICKS / f"ticks_{SYMBOL}_{day}_{hour:02d}h.jsonl"
        ticks.extend(load_jsonl(path))
    ticks.sort(key=lambda t: int(t["timestamp_msc"]))
    return ticks


def _bucket_ticks(ticks: list[dict[str, Any]]) -> dict[str, list[dict]]:
    ticks_by_bar: dict[str, list[dict]] = {}
    for t in ticks:
        if t.get("bid") is None or t.get("ask") is None:
            continue
        bid = float(t["bid"])
        ask = float(t["ask"])
        if ask < bid:
            continue  # reject crossed; do not manufacture
        ts = t["timestamp_utc"]
        minute = int(ts[14:16])
        floored = minute - (minute % 5)
        bar_t = f"{ts[:14]}{floored:02d}:00"
        row = {
            "epoch_ms": int(t["timestamp_msc"]),
            "timestamp_utc": ts,
            "bid": bid,
            "ask": ask,
        }
        ticks_by_bar.setdefault(bar_t, []).append(row)
    return ticks_by_bar


def load_day(day: str) -> dict[str, Any]:
    m5_path = PHASE40_RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl"
    h1_path = PHASE40_RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl"
    bars = load_jsonl(m5_path)
    h1_bars = load_jsonl(h1_path)
    ticks = load_ticks_day(day)
    ticks_by_bar = _bucket_ticks(ticks)
    spreads = [float(t["ask"]) - float(t["bid"]) for t in ticks if t.get("ask") is not None and t.get("bid") is not None]

    epochs = [int(b["time_epoch"]) for b in bars]
    missing = 0
    for i in range(1, len(epochs)):
        d = epochs[i] - epochs[i - 1]
        if d != 300 and 0 < d < 1800:
            missing += 1

    quality = "OK"
    if not bars:
        quality = "NO_M5"
    elif not ticks:
        quality = "NO_TICKS"
    elif not h1_bars:
        quality = "NO_H1"
    elif missing:
        quality = "M5_UNEXPECTED_GAPS"

    h1_completed_before_day = [
        b for b in h1_bars if (b.get("close_time_utc") or "") < f"{day} 00:00:00"
    ]

    return {
        "day": day,
        "bars": bars,
        "h1_bars": h1_bars,
        "ticks": ticks,
        "ticks_by_bar": ticks_by_bar,
        "m5_n": len(bars),
        "h1_n": len(h1_bars),
        "h1_warmup_completed_before_day": len(h1_completed_before_day),
        "tick_n": len(ticks),
        "tick_first": ticks[0]["timestamp_utc"] if ticks else None,
        "tick_last": ticks[-1]["timestamp_utc"] if ticks else None,
        "missing_m5_unexpected_gaps": missing,
        "spread_median": _pct(spreads, 50),
        "spread_p95": _pct(spreads, 95),
        "spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
        "data_quality_status": quality,
    }


def eligible_slots_for_day(day_payload: dict[str, Any], feat_bundle: dict[str, Any]) -> dict[str, Any]:
    """Count data-prerequisite slots (not trades)."""
    times = feat_bundle["feature_times"]
    ticks_by_bar = day_payload["ticks_by_bar"]
    h13 = mr = 0
    h13_fail = mr_fail = 0
    for i, t in enumerate(times):
        if i + HORIZON_BARS >= len(times):
            continue
        horizon = times[i + 1 : i + 1 + HORIZON_BARS]
        path_ok = all(bt in ticks_by_bar and ticks_by_bar[bt] for bt in horizon)
        h1_ok = feat_bundle["h1_ready_at"].get(t, False)
        h13_feat = i >= 20 and feat_bundle["features"][t].get("ema_20") is not None
        mr_feat = (
            i >= 48
            and feat_bundle["features"][t].get("atr_14_pct") is not None
            and feat_bundle["features"][t].get("volatility_ratio_12_48") is not None
        )
        if h13_feat and h1_ok and path_ok:
            h13 += 1
        else:
            h13_fail += 1
        if mr_feat and path_ok:
            mr += 1
        else:
            mr_fail += 1
    return {
        "day": day_payload["day"],
        "H13_C_eligible_slots": h13,
        "H13_C_ineligible": h13_fail,
        "mean_reversion_eligible_slots": mr,
        "mean_reversion_ineligible": mr_fail,
        "note": "Eligible slots ≠ generated trades",
    }


def build_eligibility_table(days: list[str] | None = None) -> dict[str, Any]:
    from phase41.features import build_feature_bundle

    days = days or list(TARGET_DATES)
    rows = []
    for day in days:
        d = load_day(day)
        feat = build_feature_bundle(d["bars"], d["h1_bars"])
        elig = eligible_slots_for_day(d, feat)
        rows.append(
            {
                **elig,
                "m5_n": d["m5_n"],
                "h1_n": d["h1_n"],
                "h1_warmup_before_day": d["h1_warmup_completed_before_day"],
                "tick_n": d["tick_n"],
                "tick_first": d["tick_first"],
                "tick_last": d["tick_last"],
                "spread_median": d["spread_median"],
                "data_quality_status": d["data_quality_status"],
            }
        )
    return {
        "n_dates": len(rows),
        "rows": rows,
        "H13_C_total_eligible_slots": sum(r["H13_C_eligible_slots"] for r in rows),
        "mean_reversion_total_eligible_slots": sum(r["mean_reversion_eligible_slots"] for r in rows),
        "caveat": "Phase40 full-session ticks; eligibility is data prerequisites only.",
    }
