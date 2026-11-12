"""Intrabar TP/SL ordering ambiguity using tick sequences."""

from __future__ import annotations

from typing import Any

from phase34.progress import write_json


def analyze_intrabar(ticks: list[dict[str, Any]], acquisition: dict[str, Any]) -> dict[str, Any]:
    """Document what tick paths can and cannot resolve for barrier ordering."""
    n = len(ticks)
    # Tick-level ordering is available within acquired hours; gaps between sparse/missing hours are not.
    failed_hours = (acquisition.get("totals") or {}).get("failed_hours", 0)
    empty_hours = (acquisition.get("totals") or {}).get("empty_hours", 0)
    incomplete_days = acquisition.get("incomplete_trading_days") or []

    report = {
        "tick_level_ordering_available": n > 0,
        "scope": (
            "Within each acquired non-empty hour, ticks are time-ordered and can support "
            "pathwise first-touch analysis for that hour. Across missing hours / gaps, paths are unresolved."
        ),
        "buy_barriers": {
            "TP_trigger_price": "bid reaches TP (close long at bid)",
            "SL_trigger_price": "bid reaches SL",
            "note": "BUY cannot exit at ask; using mid/M5 OHLC alone is insufficient.",
        },
        "sell_barriers": {
            "TP_trigger_price": "ask reaches TP (close short at ask)",
            "SL_trigger_price": "ask reaches SL",
            "note": "SELL cannot exit at bid for cover; ask-side path required.",
        },
        "m5_ohlc_alone_proves_first_touch": False,
        "gaps_and_unavailable_hours": {
            "failed_hours": failed_hours,
            "empty_hours": empty_hours,
            "incomplete_days": incomplete_days,
            "effect": "Unresolved execution paths across gaps; do not invent fills.",
        },
        "conservative_handling": [
            "If both TP and SL are touchable within an M5 bar without tick path → AMBIGUOUS.",
            "If tick path exists for the bar interval → determine first touch on the executable side.",
            "If gap crosses barrier level → mark UNRESOLVED (do not assume fill).",
            "Do not rewrite Phase 0–33 labels in this phase.",
        ],
        "labels_rewritten": False,
        "classification": "TICK_PATH_PARTIAL_COVERAGE",
    }
    write_json("intrabar_ambiguity.json", report)
    return report
