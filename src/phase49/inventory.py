"""Inventory of verified source fields from acquired archives."""

from __future__ import annotations

from typing import Any

from phase49.data import load_m5, load_ticks
from phase49.storage import load_jsonl
from phase49.constants import RAW_H1, SYMBOL


def inventory_fields(sample_day: str) -> dict[str, Any]:
    m5 = load_m5(sample_day)
    ticks = load_ticks(sample_day)
    h1 = load_jsonl(RAW_H1 / f"h1_{SYMBOL}_{sample_day}_warmup.jsonl")
    m5_keys = sorted(m5[0].keys()) if m5 else []
    tick_keys = sorted(ticks[0].keys()) if ticks else []
    h1_keys = sorted(h1[0].keys()) if h1 else []
    real_vol = [float(r.get("real_volume") or 0) for r in m5[:50]] if m5 else []
    return {
        "sample_day": sample_day,
        "m5_fields": m5_keys,
        "tick_fields": tick_keys,
        "h1_fields": h1_keys,
        "real_volume_nonzero_frac_sample": (
            sum(1 for v in real_vol if v > 0) / len(real_vol) if real_vol else None
        ),
        "vwap_eligible": False,
        "note": "VWAP excluded: real_volume not verified exchange volume",
    }
