"""Assemble broker economics matrix from sub-models."""

from __future__ import annotations

from typing import Any

from phase64_10.commission import investigate_commission
from phase64_10.constants import (
    CONFLICTING,
    UNKNOWN,
    UNKNOWN_FOR_EXECUTION,
    VERIFIED,
    canonical_json_sha256,
)
from phase64_10.cost_model import build_cost_model
from phase64_10.margin_model import build_margin_model
from phase64_10.sessions import build_session_model
from phase64_10.swap_analysis import analyze_swap_conflict


def build_economics_bundle(
    *,
    observed_spread_points: float = 240.0,
    n_trade_deals: int = 0,
    price: float = 2650.0,
) -> dict[str, Any]:
    commission = investigate_commission(n_trade_deals=n_trade_deals)
    margin = build_margin_model(price=price)
    sessions = build_session_model()
    swap = analyze_swap_conflict()

    cost = build_cost_model(
        spread_points=observed_spread_points,
        spread_status=VERIFIED,
        slippage_status=UNKNOWN,
        commission_status=commission["actual_commission_status"],
        commission=commission["actual_commission_observed"],
        swap_status=UNKNOWN_FOR_EXECUTION if swap["conflict_status"] != "resolved" else VERIFIED,
        swap=CONFLICTING,
        other_status=UNKNOWN,
        financing_status=UNKNOWN,
    )

    matrix = [
        {"item": "spread", "status": VERIFIED, "value": observed_spread_points, "blocks": False},
        {"item": "slippage", "status": UNKNOWN, "value": UNKNOWN, "blocks": True},
        {
            "item": "commission_account_specific",
            "status": commission["actual_commission_status"],
            "value": commission["actual_commission_observed"],
            "blocks": True,
        },
        {
            "item": "commission_published",
            "status": commission["published_commission"]["status"],
            "value": commission["published_commission"]["value"],
            "blocks": True,
        },
        {"item": "swap", "status": swap["status_for_execution"], "value": "CONFLICT_PRESERVED", "blocks": True},
        {"item": "margin", "status": margin["MARGIN_MODEL"], "value": margin["MARGIN_MODEL"], "blocks": True},
        {"item": "sessions", "status": sessions["programmatic_status"], "value": sessions["completeness"], "blocks": True},
        {"item": "other_charges", "status": UNKNOWN, "value": UNKNOWN, "blocks": True},
    ]

    out = {
        "commission": commission,
        "margin": margin,
        "sessions": sessions,
        "swap": swap,
        "cost_model": cost,
        "matrix": matrix,
        "n_blocking": sum(1 for r in matrix if r["blocks"]),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
