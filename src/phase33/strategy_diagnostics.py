"""Frozen-signal strategy re-eval — only if bid/ask coverage is sufficient."""

from __future__ import annotations

from typing import Any

from phase33.constants import RESEARCH_CUTOFF_UTC, SAMPLE_DAYS, SAMPLE_HOURS_UTC
from phase33.progress import write_json

STRATEGIES = [
    "H13_C",
    "vol_norm_momentum",
    "m15_trend_m5_trigger",
    "robust_mad_reversion",
    "body_persistence",
]


def assess_coverage(ticks: list[dict[str, Any]], candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Strategy diagnostics need contiguous multi-month M5 bid/ask covering research trades."""
    n_candles = len(candles)
    if not ticks:
        return {
            "sufficient": False,
            "reason": "no_bid_ask_ticks",
        }
    # Heuristic: full strategy ledger spans years of M5; sample hours across few days are diagnostic only.
    # Require >= ~10_000 M5 candles with bid/ask for even a thin diagnostic — sample will be far below.
    min_candles_for_eval = 10_000
    return {
        "sufficient": n_candles >= min_candles_for_eval,
        "n_m5_candles": n_candles,
        "min_candles_required": min_candles_for_eval,
        "sample_days": SAMPLE_DAYS,
        "sample_hours_utc": SAMPLE_HOURS_UTC,
        "reason": (
            None
            if n_candles >= min_candles_for_eval
            else (
                "Historical bid/ask coverage is a bounded diagnostic sample "
                f"({n_candles} M5 candles across sparse hours). "
                "Insufficient to re-price frozen strategy trades across the approved research window "
                f"ending {RESEARCH_CUTOFF_UTC}. Skipping strategy diagnostic to avoid false precision."
            )
        ),
    }


def run_strategy_diagnostics(
    ticks: list[dict[str, Any]],
    candles: list[dict[str, Any]],
) -> dict[str, Any]:
    coverage = assess_coverage(ticks, candles)
    if not coverage["sufficient"]:
        report = {
            "executed": False,
            "skipped": True,
            "skip_reason": coverage["reason"],
            "coverage": coverage,
            "strategies": STRATEGIES,
            "signals_modified": False,
            "thresholds_modified": False,
            "pooled_oos_optimization": False,
            "promotion": False,
            "comparisons": None,
        }
        write_json("strategy_diagnostics.json", report)
        return report

    # Intentionally unreachable with Phase33 bounded sample; kept for completeness.
    report = {
        "executed": False,
        "skipped": True,
        "skip_reason": "Coverage gate passed unexpectedly; full re-eval not implemented in Phase33 bounded scope.",
        "coverage": coverage,
        "strategies": STRATEGIES,
        "signals_modified": False,
        "promotion": False,
    }
    write_json("strategy_diagnostics.json", report)
    return report
