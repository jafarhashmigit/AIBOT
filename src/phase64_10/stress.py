"""Execution-cost stress framework — research diagnostic, not edge proof."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import (
    ESTIMATED,
    STRESS_VERSION,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    UNKNOWN,
    VERIFIED,
    VERIFIED_TICK_VALUE,
    canonical_json_sha256,
)


def _spread_cost_usd(*, spread_points: float, volume: float = 0.01) -> float:
    # tick_value is per 0.01 lot per tick; points≈ticks when tick_size=point
    return float(spread_points) * float(VERIFIED_TICK_VALUE) * (float(volume) / 0.01)


def _swap_cost_usd(*, swap_points: float, volume: float = 0.01, nights: int = 1) -> float:
    # POINTS swap: monetary ≈ swap_points * tick_value * (volume/0.01) per night (simplified)
    return abs(float(swap_points)) * float(VERIFIED_TICK_VALUE) * (float(volume) / 0.01) * nights


def build_stress_framework(
    *,
    observed_spread_points: float = 240.0,
    volume: float = 0.01,
    expected_edge_usd: float | None = None,
) -> dict[str, Any]:
    """
    Answer: at what transaction-cost level does a future strategy EV become non-positive?
    expected_edge_usd is a hypothetical research input — not a proven edge.
    """
    baseline = {
        "name": "baseline_verified_only",
        "spread": {"status": VERIFIED, "points": observed_spread_points, "usd": _spread_cost_usd(spread_points=observed_spread_points, volume=volume)},
        "slippage": {"status": UNKNOWN, "usd": UNKNOWN, "note": "no fills"},
        "commission": {"status": UNKNOWN, "usd": UNKNOWN},
        "swap": {"status": "UNKNOWN_FOR_EXECUTION", "usd": UNKNOWN},
        "total_known_usd": _spread_cost_usd(spread_points=observed_spread_points, volume=volume),
        "complete": False,
    }

    conservative_spread_pts = observed_spread_points * 2.0
    cons_spread = {
        "name": "conservative_spread",
        "spread_points": conservative_spread_pts,
        "usd": _spread_cost_usd(spread_points=conservative_spread_pts, volume=volume),
        "label": ESTIMATED,
        "note": "2x observed snapshot — stress only, not broker fact",
    }

    slip = {
        "name": "slippage_stress",
        "proxy_points": 50.0,
        "usd": _spread_cost_usd(spread_points=50.0, volume=volume),
        "label": ESTIMATED,
        "note": "Proxy assumption only — not observed fills",
    }

    commission_stress = {
        "name": "commission_stress",
        "usd": 0.5,  # hypothetical per side stress dollar — labeled uncertain
        "label": ESTIMATED,
        "account_applicability": UNKNOWN,
        "note": "Not from verified account schedule; stress proxy only",
    }

    swap_adverse = min(SWAP_LONG_PHASE63, SWAP_LONG_PHASE64_7)  # more negative
    swap_stress = {
        "name": "swap_stress",
        "swap_points_used": swap_adverse,
        "nights": 1,
        "usd": _swap_cost_usd(swap_points=swap_adverse, volume=volume, nights=1),
        "label": ESTIMATED,
        "note": "Uses more adverse of conflicting observations without claiming reconciled broker fact",
        "observations_preserved": [SWAP_LONG_PHASE63, SWAP_LONG_PHASE64_7],
    }

    combined_usd = (
        cons_spread["usd"]
        + slip["usd"]
        + float(commission_stress["usd"])
        + float(swap_stress["usd"])
    )
    combined = {
        "name": "combined_stress",
        "usd": combined_usd,
        "parts": ["conservative_spread", "slippage_stress", "commission_stress", "swap_stress"],
        "label": ESTIMATED,
    }

    # EV break-even diagnostic
    edge = expected_edge_usd
    breakeven = {
        "question": "At what transaction-cost level does future strategy EV become non-positive?",
        "hypothetical_expected_edge_usd": edge if edge is not None else UNKNOWN,
        "combined_stress_usd": combined_usd,
        "baseline_known_cost_usd": baseline["total_known_usd"],
        "ev_nonpositive_under_combined_stress": (
            edge is not None and float(edge) <= combined_usd
        )
        if edge is not None
        else UNKNOWN,
        "note": "Research diagnostic only — does not prove strategy profitability or manufacture an edge",
    }

    out = {
        "stress_version": STRESS_VERSION,
        "volume": volume,
        "observed_spread_points": observed_spread_points,
        "scenarios": {
            "baseline": baseline,
            "conservative_spread": cons_spread,
            "slippage_stress": slip,
            "commission_stress": commission_stress,
            "swap_stress": swap_stress,
            "combined_stress": combined,
        },
        "breakeven_diagnostic": breakeven,
        "never_use_stress_as_broker_fact": True,
        "never_manufacture_edge": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
