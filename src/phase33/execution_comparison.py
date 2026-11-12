"""Compare frozen cost model vs observed bid/ask spreads — no invented slippage."""

from __future__ import annotations

from typing import Any

from phase33.constants import (
    EXTRA_COST_PER_SIDE,
    EXTRA_COST_ROUND_TRIP,
    MIN_SPREAD_POINTS,
    POINT_SIZE,
)
from phase33.progress import write_json


def buy_entry_ask(ask: float) -> float:
    return ask


def buy_exit_bid(bid: float) -> float:
    return bid


def sell_entry_bid(bid: float) -> float:
    return bid


def sell_exit_ask(ask: float) -> float:
    return ask


def round_trip_spread_cost_buy(entry_ask: float, exit_bid: float) -> float:
    """BUY pays ask on entry and receives bid on exit → spread cost = entry_ask - exit_bid path dependent.
    Instantaneous round-trip at same tick: ask - bid.
    """
    return entry_ask - exit_bid


def classify_intrabar_ambiguity() -> dict[str, Any]:
    return {
        "intrabar_path_known": False,
        "assumption_forbidden": [
            "market orders always fill at candle open",
            "barrier touches guarantee executable fills",
            "invented slippage beyond observed spread",
        ],
        "classification": "INTRABAR_ORDERING_AMBIGUOUS",
        "tp_sl_semantics": {
            "BUY_TP": "trigger when bid reaches TP (sell to close at bid)",
            "BUY_SL": "trigger when bid reaches SL",
            "SELL_TP": "trigger when ask reaches TP (buy to close at ask)",
            "SELL_SL": "trigger when ask reaches SL",
            "note": "Without tick path inside M5, first-touch TP vs SL remains ambiguous.",
        },
    }


def compare_execution_models(spread_report: dict[str, Any]) -> dict[str, Any]:
    floor_usd = MIN_SPREAD_POINTS * POINT_SIZE
    overall = spread_report.get("overall_usd") or {}
    median = overall.get("median")
    mean = overall.get("mean")
    p95 = overall.get("p95")

    # Frozen model: spread floor applied to bar spread column + $0.05/side extra.
    # label_m5: long entry = open + spread + 0.05; long exit uses bid-side (open/high/low - 0.05).
    # Short entry = open - 0.05; short exit uses ask-side (+ spread + 0.05).
    # Spread is NOT double-counted as a separate round-trip add-on beyond the bid/ask synthetic.
    frozen = {
        "spread_floor_points": MIN_SPREAD_POINTS,
        "spread_floor_usd": floor_usd,
        "extra_round_trip_usd": EXTRA_COST_ROUND_TRIP,
        "extra_per_side_usd": EXTRA_COST_PER_SIDE,
        "implementation": "label_m5 / phase18 barrier — floored bar spread embedded in fill prices + $0.05/side",
        "double_counting_check": {
            "spread_also_added_as_flat_fee": False,
            "extra_is_separate_from_spread": True,
            "verified_against": "src/label_m5.py EXTRA_COST_PER_SIDE and floored spread in entry/exit",
        },
    }

    observed = {
        "median_spread_usd": median,
        "mean_spread_usd": mean,
        "p95_spread_usd": p95,
        "fraction_below_floor": (spread_report.get("vs_frozen_spread_floor") or {}).get(
            "fraction_ticks_below_floor"
        ),
    }

    comparison_notes = []
    if median is not None and median == median:  # not NaN
        if median < floor_usd:
            comparison_notes.append(
                f"Observed median spread ${median:.4f} < frozen floor ${floor_usd:.2f} — "
                "floor is conservative vs this Dukascopy sample median."
            )
        else:
            comparison_notes.append(
                f"Observed median spread ${median:.4f} >= frozen floor ${floor_usd:.2f} — "
                "floor may understate typical Dukascopy sample costs."
            )
        if p95 is not None and p95 > floor_usd:
            comparison_notes.append(
                f"P95 spread ${p95:.4f} exceeds floor — tail costs not captured by a constant floor."
            )

    report = {
        "frozen_cost_model": frozen,
        "observed_spread_distribution_summary": observed,
        "bid_ask_aware_fills": {
            "BUY_entry": "ask",
            "BUY_exit": "bid",
            "SELL_entry": "bid",
            "SELL_exit": "ask",
            "helpers": {
                "buy_entry_ask": buy_entry_ask(1900.50) if False else "buy_entry_ask(ask)",
                "sell_entry_bid": "sell_entry_bid(bid)",
            },
        },
        "unobservable_costs": [
            "broker commission beyond modeled $0.05/side",
            "latency / requote",
            "slippage beyond touch",
            "partial fills",
        ],
        "intrabar_ambiguity": classify_intrabar_ambiguity(),
        "comparison_notes": comparison_notes,
        "single_average_spread_used_as_substitute": False,
        "slippage_invented": False,
    }
    write_json("execution_comparison.json", report)
    return report
