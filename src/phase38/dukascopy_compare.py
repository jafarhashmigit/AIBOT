"""Compare MT5 canonical ticks vs existing local Phase34 Dukascopy (no new downloads)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from phase38.constants import PHASE34_TICKS, RAW_TICKS_DIR, SYMBOL, TICK_SAMPLE_START_HOUR_UTC
from phase38.storage import load_jsonl


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def compare_overlap_days() -> dict[str, Any]:
    results = []
    if not RAW_TICKS_DIR.exists():
        return {"possible": False, "reason": "no_phase38_ticks", "results": []}
    for p in sorted(RAW_TICKS_DIR.glob(f"ticks_{SYMBOL}_*_*.jsonl")):
        # ticks_XAUUSD_YYYY-MM-DD_12h.jsonl
        parts = p.stem.split("_")
        day = parts[2] if len(parts) >= 3 else None
        if not day:
            continue
        duka_path = PHASE34_TICKS / f"{day}.jsonl"
        mt5 = load_jsonl(p)
        if not duka_path.is_file():
            results.append({"day": day, "possible": False, "reason": "no_local_phase34_ticks"})
            continue
        duka = []
        for line in duka_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                duka.append(json.loads(line))
        mt5_sp = [float(t["ask"]) - float(t["bid"]) for t in mt5 if t.get("ask") is not None and t.get("bid") is not None]
        duka_sp = [float(t["ask"]) - float(t["bid"]) for t in duka if t.get("ask") is not None and t.get("bid") is not None]
        results.append(
            {
                "day": day,
                "possible": True,
                "mt5_n": len(mt5),
                "dukascopy_n": len(duka),
                "both_bid_ask": True,
                "mt5_window": f"{TICK_SAMPLE_START_HOUR_UTC:02d}h+bounded",
                "dukascopy_window": "full local day where available",
                "spread_median_mt5": _pct(mt5_sp, 50),
                "spread_median_dukascopy": _pct(duka_sp, 50),
                "spread_p95_mt5": _pct(mt5_sp, 95),
                "spread_p95_dukascopy": _pct(duka_sp, 95),
                "exact_parity": False,
                "note": "Not tick-aligned; density not directly comparable across unequal windows",
            }
        )
    return {
        "possible": any(r.get("possible") for r in results),
        "results": results,
        "caveat": "Neither source claimed as live broker execution truth",
    }
