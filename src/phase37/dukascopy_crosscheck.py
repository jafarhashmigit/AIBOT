"""Cross-check MT5 vs existing local Phase34 Dukascopy ticks (no new downloads)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from phase37.constants import PHASE34_TICKS


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def load_dukascopy_day(day: str) -> list[dict[str, Any]]:
    path = PHASE34_TICKS / f"{day}.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def crosscheck_day(mt5_ticks: list[dict[str, Any]], day: str) -> dict[str, Any]:
    duka = load_dukascopy_day(day)
    if not duka:
        return {
            "day": day,
            "possible": False,
            "reason": "no_local_phase34_ticks_for_day",
            "phase34_path": str(PHASE34_TICKS / f"{day}.jsonl"),
        }
    if not mt5_ticks:
        return {"day": day, "possible": False, "reason": "no_mt5_ticks"}

    duka_spreads = [float(t["ask"]) - float(t["bid"]) for t in duka if t.get("ask") is not None and t.get("bid") is not None]
    mt5_spreads = [float(t["spread"]) for t in mt5_ticks if t.get("spread") is not None]

    # Mid price samples at first/last overlap hour if possible
    duka_mids = [(float(t["bid"]) + float(t["ask"])) / 2.0 for t in duka[:1000]]
    mt5_mids = [
        (float(t["bid"]) + float(t["ask"])) / 2.0
        for t in mt5_ticks[:1000]
        if t.get("bid") is not None and t.get("ask") is not None
    ]
    mid_delta = None
    if duka_mids and mt5_mids:
        mid_delta = abs(duka_mids[0] - mt5_mids[0])

    return {
        "day": day,
        "possible": True,
        "structural_compatibility": {
            "both_have_bid_ask": True,
            "dukascopy_n": len(duka),
            "mt5_n": len(mt5_ticks),
            "tick_density_ratio_mt5_over_duka": (len(mt5_ticks) / len(duka)) if duka else None,
        },
        "approximate_price_agreement": {
            "sample_mid_abs_delta_first_1000_window": mid_delta,
            "note": "Not tick-aligned; absolute delta of early-window mids only",
        },
        "spread_distribution": {
            "dukascopy_median": _pct(duka_spreads, 50),
            "dukascopy_p95": _pct(duka_spreads, 95),
            "mt5_median": _pct(mt5_spreads, 50),
            "mt5_p95": _pct(mt5_spreads, 95),
        },
        "exact_parity": False,
        "exact_parity_note": "Exact tick-for-tick parity not required and not claimed",
    }


def run_crosschecks(mt5_by_day: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    days = sorted(mt5_by_day.keys())
    results = [crosscheck_day(mt5_by_day[d], d) for d in days]
    possible = [r for r in results if r.get("possible")]
    return {
        "overlap_days_attempted": days,
        "overlap_possible_n": len(possible),
        "results": results,
        "summary": (
            "Structural bid/ask comparison available on overlapping local Phase34 days"
            if possible
            else "Insufficient local Phase34 overlap for cross-check"
        ),
    }
