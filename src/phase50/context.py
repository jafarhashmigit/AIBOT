"""Preregistered compact context representation — no outcome-based selection."""

from __future__ import annotations

from typing import Any

from phase50.constants import MARKET_STATE_VERSION, SPREAD_ATR_EDGES


def build_context(features: dict[str, Any]) -> dict[str, Any]:
    """
    Compact buckets from Phase49 feature IDs when present:
      - spread_atr_bucket: low/mid/high
      - overlap: 0/1
      - vol_accel_sign: -1/0/1
    """
    spread = features.get("E02_spread_atr")
    if spread is None:
        spread_bucket = "unknown"
    elif float(spread) < SPREAD_ATR_EDGES[0]:
        spread_bucket = "low"
    elif float(spread) < SPREAD_ATR_EDGES[1]:
        spread_bucket = "mid"
    else:
        spread_bucket = "high"

    overlap = features.get("D03_overlap")
    overlap_b = "1" if overlap is not None and float(overlap) >= 0.5 else "0"

    va = features.get("C03_vol_accel")
    if va is None:
        vol_sign = "0"
    elif float(va) > 1.05:
        vol_sign = "+1"
    elif float(va) < 0.95:
        vol_sign = "-1"
    else:
        vol_sign = "0"

    bucket_id = f"spr:{spread_bucket}|ov:{overlap_b}|va:{vol_sign}"
    return {
        "market_state_version": MARKET_STATE_VERSION,
        "bucket_id": bucket_id,
        "spread_atr_bucket": spread_bucket,
        "overlap": overlap_b,
        "vol_accel_sign": vol_sign,
    }


def context_id(ctx: dict[str, Any]) -> str:
    return str(ctx.get("bucket_id") or "unknown")
