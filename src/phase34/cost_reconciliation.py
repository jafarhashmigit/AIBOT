"""Execution-cost reconciliation vs frozen assumptions — no label mutation."""

from __future__ import annotations

from typing import Any

from phase34.constants import (
    EXTRA_COST_PER_SIDE_FROZEN,
    MIN_SPREAD_POINTS_FROZEN,
    POINT_SIZE,
)
from phase34.progress import write_json


def reconcile_costs(spread_report: dict[str, Any]) -> dict[str, Any]:
    floor_usd = MIN_SPREAD_POINTS_FROZEN * POINT_SIZE
    overall = spread_report.get("overall_usd") or {}
    median = overall.get("median")
    mean = overall.get("mean")
    p25 = overall.get("p25") if "p25" in overall else None
    # use p50 from report
    p50 = overall.get("p50") or median
    p75 = overall.get("p75")
    p95 = overall.get("p95")

    # Scenarios must be assumption-documented — not silent changes to frozen labels.
    scenarios = {
        "optimistic": {
            "spread_usd": p50,
            "extra_per_side_usd": 0.0,
            "assumption": "Fill at median observed Dukascopy spread; no extra commission/slippage evidence.",
            "supported_by": "observed median spread distribution",
            "slippage_verified": False,
        },
        "baseline": {
            "spread_usd": p75 or mean,
            "extra_per_side_usd": EXTRA_COST_PER_SIDE_FROZEN,
            "assumption": (
                "Use P75 observed spread as typical executable round-trip spread cost proxy; "
                "retain frozen $0.05/side as unverified commission/friction placeholder."
            ),
            "supported_by": "observed P75 + frozen extra-cost constant (not independently verified as broker fee)",
            "slippage_verified": False,
        },
        "conservative": {
            "spread_usd": p95,
            "extra_per_side_usd": EXTRA_COST_PER_SIDE_FROZEN,
            "assumption": (
                "Use P95 observed spread; keep $0.05/side extra. Does not invent additional slippage."
            ),
            "supported_by": "observed P95 + frozen extra-cost constant",
            "slippage_verified": False,
        },
    }

    vs_floor = {
        "frozen_floor_points": MIN_SPREAD_POINTS_FROZEN,
        "frozen_floor_usd": floor_usd,
        "observed_median_usd": median,
        "floor_vs_median": (
            "UNDERSTATES_OBSERVED_MEDIAN"
            if median is not None and median > floor_usd
            else "AT_OR_ABOVE_MEDIAN"
        ),
        "do_not_assume_floor_realistic": True,
        "do_not_assume_extra_cost_realistic": True,
    }

    report = {
        "distinctions": {
            "bid_ask_spread": "ask - bid from ticks — observed",
            "commission_fees": "not independently verified for Dukascopy vs project broker",
            "slippage": "UNVERIFIED — no evidence invented",
            "entry_exit_assumptions": {
                "BUY_entry": "ask",
                "BUY_exit": "bid",
                "SELL_entry": "bid",
                "SELL_exit": "ask",
            },
        },
        "frozen_assumptions": {
            "spread_floor_points": MIN_SPREAD_POINTS_FROZEN,
            "spread_floor_usd": floor_usd,
            "extra_per_side_usd": EXTRA_COST_PER_SIDE_FROZEN,
            "labels_modified": False,
            "strategy_costs_modified": False,
            "double_counting_spread": False,
        },
        "vs_frozen_floor": vs_floor,
        "scenarios": scenarios,
        "recommendation": (
            "Do not treat the frozen $0.15 floor as realistic for Dukascopy-sample offline evaluation; "
            "use distributional spreads. Extra $0.05/side remains an unverified placeholder."
        ),
    }
    write_json("execution_cost_comparison.json", report)
    return report
