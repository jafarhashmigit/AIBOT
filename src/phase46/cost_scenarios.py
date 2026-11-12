"""Explicit execution-cost scenarios. Demo ≠ live. Unknown stays unknown."""

from __future__ import annotations

from typing import Any

# Registry frozen into research contract. Hypothetical stress is labeled — not live truth.
COST_SCENARIO_REGISTRY: dict[str, dict[str, Any]] = {
    "OBSERVED_BIDASK_ONLY": {
        "id": "OBSERVED_BIDASK_ONLY",
        "description": (
            "Net = gross from bid/ask fills. Observed spread is embedded in fills. "
            "Commission and slippage remain UNKNOWN (not invented)."
        ),
        "spread_handling": "embedded_in_bidask_fills",
        "subtract_observed_spread_again": False,
        "commission_usd_per_side": None,  # UNKNOWN
        "slippage_usd_per_side": None,  # UNKNOWN
        "spread_widen_mult": 1.0,
        "additional_stress_usd": 0.0,
        "live_broker_truth": False,
    },
    "STRESS_SPREAD_WIDEN_1_5X": {
        "id": "STRESS_SPREAD_WIDEN_1_5X",
        "description": (
            "Hypothetical: add (0.5 × (entry_spread + exit_spread)) on top of embedded fills. "
            "Not observed live cost. Commission/slippage still UNKNOWN."
        ),
        "spread_handling": "embedded_plus_hypothetical_widen",
        "subtract_observed_spread_again": False,
        "commission_usd_per_side": None,
        "slippage_usd_per_side": None,
        "spread_widen_mult": 1.5,
        "additional_stress_usd": 0.0,
        "live_broker_truth": False,
    },
    "STRESS_LABELED_FRICTION_PROXY": {
        "id": "STRESS_LABELED_FRICTION_PROXY",
        "description": (
            "Configurable labeled friction proxy for sensitivity only. "
            "Values are NOT claimed MetaQuotes-Demo or live broker measurements. "
            "Documented as RESEARCH_PROXY_UNKNOWN_LIVE."
        ),
        "spread_handling": "embedded_plus_hypothetical_widen",
        "subtract_observed_spread_again": False,
        # Explicit research proxies — NOT invented as 'true' commission/slippage
        "commission_usd_per_side": 0.0,
        "slippage_usd_per_side": 0.05,
        "spread_widen_mult": 1.25,
        "additional_stress_usd": 0.0,
        "cost_provenance": "RESEARCH_PROXY_UNKNOWN_LIVE",
        "live_broker_truth": False,
    },
}


def apply_scenario_costs(
    *,
    gross_pnl: float,
    risk_amount: float,
    entry_spread: float,
    exit_spread: float,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """
    Compute net from gross under scenario without double-counting embedded spread.

    Observed spread is already in bid/ask gross_pnl. Additional cost only from
    widen_mult > 1, and any labeled commission/slippage proxies.
    """
    widen = float(scenario.get("spread_widen_mult") or 1.0)
    base_spread = float(entry_spread) + float(exit_spread)
    # Only the incremental widen beyond 1.0 is additive (avoid double-count)
    extra_spread = base_spread * max(0.0, widen - 1.0)

    comm = scenario.get("commission_usd_per_side")
    slip = scenario.get("slippage_usd_per_side")
    commission_roundtrip = None if comm is None else 2.0 * float(comm)
    slippage_roundtrip = None if slip is None else 2.0 * float(slip)

    known_extra = extra_spread + float(scenario.get("additional_stress_usd") or 0.0)
    if commission_roundtrip is not None:
        known_extra += commission_roundtrip
    if slippage_roundtrip is not None:
        known_extra += slippage_roundtrip

    net_pnl = float(gross_pnl) - known_extra
    net_r = (net_pnl / risk_amount) if risk_amount > 0 else None

    unknown_components = []
    if comm is None:
        unknown_components.append("commission")
    if slip is None:
        unknown_components.append("slippage")

    return {
        "scenario_id": scenario["id"],
        "spread_cost_embedded_in_bidask": True,
        "spread_cost_additional": extra_spread,
        "commission_roundtrip": commission_roundtrip,
        "slippage_roundtrip": slippage_roundtrip,
        "total_modeled_extra_cost": known_extra,
        "unknown_cost_components": unknown_components,
        "net_pnl": net_pnl,
        "net_r": net_r,
        "live_broker_truth": False,
    }
