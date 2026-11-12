"""Independent reload / recompute validation for cached MT5 samples."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase37.bars import analyze_m5_bars
from phase37.cache import load_jsonl
from phase37.ticks import analyze_ticks


def validate_bars_reload(path: Path, original_analysis: dict[str, Any], original_n: int) -> dict[str, Any]:
    rows = load_jsonl(path)
    analysis = analyze_m5_bars(rows)
    mismatches = []
    if len(rows) != original_n:
        mismatches.append(f"n_bars {len(rows)} != {original_n}")
    for key in ("duplicate_timestamps", "out_of_order_timestamps", "invalid_ohlc", "pass_ohlc", "pass_chrono"):
        if analysis.get(key) != original_analysis.get(key):
            mismatches.append(f"{key}: reload={analysis.get(key)} orig={original_analysis.get(key)}")
    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "reload_n": len(rows),
        "reload_analysis": analysis,
    }


def validate_ticks_reload(path: Path, original_analysis: dict[str, Any], original_n: int) -> dict[str, Any]:
    rows = load_jsonl(path)
    analysis = analyze_ticks(rows)
    mismatches = []
    if len(rows) != original_n:
        mismatches.append(f"n_ticks {len(rows)} != {original_n}")
    for key in (
        "bid_available",
        "ask_available",
        "crossed_bid_gt_ask",
        "negative_spread",
        "duplicate_timestamps_msc",
        "out_of_order_timestamps",
        "spread_median",
        "pass_chrono",
        "pass_spread",
    ):
        a, b = analysis.get(key), original_analysis.get(key)
        if isinstance(a, float) and isinstance(b, float):
            if abs(a - b) > 1e-9:
                mismatches.append(f"{key}: reload={a} orig={b}")
        elif a != b:
            mismatches.append(f"{key}: reload={a} orig={b}")
    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "reload_n": len(rows),
        "reload_analysis": {
            k: analysis.get(k)
            for k in (
                "n_ticks",
                "bid_available",
                "ask_available",
                "spread_median",
                "spread_mean",
                "spread_p95",
                "pass_chrono",
                "pass_spread",
            )
        },
    }
