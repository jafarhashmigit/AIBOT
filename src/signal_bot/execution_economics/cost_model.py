"""Versioned Exness XAUUSDm execution-cost model — unknowns never become zero."""

from __future__ import annotations

from typing import Any

from signal_bot.execution_economics.constants import (
    CONFLICTED,
    COST_MODEL_VERSION,
    NOT_APPLICABLE,
    PARTIALLY_VERIFIED,
    UNKNOWN,
    UNKNOWN_FOR_EXECUTION,
    VERIFIED,
    VERIFIED_TICK_VALUE,
    canonical_json_sha256,
)


def _comp(
    name: str,
    *,
    status: str,
    value: Any = UNKNOWN,
    unit: str | None = None,
    provenance: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    usable = status == VERIFIED
    return {
        "component": name,
        "status": status,
        "value": value,
        "unit": unit,
        "provenance": provenance,
        "usable_for_deterministic_net": usable,
        "notes": notes,
        "silently_zeroed": False,
    }


def build_cost_model(
    *,
    observed_spread_price_median: float | None,
    observed_spread_points_median: float | None,
    spread_n: int,
    commission_status: str = UNKNOWN,
    commission_value: Any = UNKNOWN,
    swap_status: str = UNKNOWN_FOR_EXECUTION,
    swap_value: Any = UNKNOWN,
    slippage_status: str = UNKNOWN,
    gap_stop_status: str = UNKNOWN,
) -> dict[str, Any]:
    if observed_spread_price_median is not None and spread_n > 0:
        spread_status = VERIFIED if spread_n >= 30 else PARTIALLY_VERIFIED
        spread_notes = (
            f"Median of {spread_n} usable live quotes (price units); "
            "sample may not represent all regimes"
        )
    else:
        spread_status = UNKNOWN
        spread_notes = "No usable live quotes"

    # Map conflicted swap
    if swap_status in (CONFLICTED, "CONFLICTING", UNKNOWN_FOR_EXECUTION):
        swap_status_norm = CONFLICTED if swap_status == CONFLICTED else UNKNOWN_FOR_EXECUTION
    else:
        swap_status_norm = swap_status

    comps = [
        _comp(
            "observed_spread",
            status=spread_status,
            value={
                "median_price": observed_spread_price_median,
                "median_points": observed_spread_points_median,
                "n": spread_n,
            },
            unit="price_and_points",
            provenance="LIVE_JOURNAL_QUOTE_SNAPSHOTS",
            notes=spread_notes,
        ),
        _comp(
            "commission",
            status=commission_status,
            value=commission_value,
            unit="account_currency_per_deal_or_lot",
            provenance="PHASE64_10_NO_TRADE_FILLS",
            notes="Do not assume zero; public schedules not account-verified",
        ),
        _comp(
            "swap",
            status=swap_status_norm,
            value=swap_value,
            unit="points_per_lot_per_day",
            provenance="PHASE64_7_AND_PHASE63_PRESERVED",
            notes="Conflict preserved; not interchangeable",
        ),
        _comp(
            "slippage",
            status=slippage_status,
            value=UNKNOWN,
            unit="price_units",
            provenance="NO_FILLS",
            notes="Guessed slippage must never be labeled verified",
        ),
        _comp(
            "gap_and_stop_execution_risk",
            status=gap_stop_status,
            value=UNKNOWN,
            unit="R_or_price",
            provenance="NONE",
            notes="Requires path/fill evidence; unknown ≠ zero",
        ),
        _comp(
            "other_fees",
            status=NOT_APPLICABLE,
            value=NOT_APPLICABLE,
            notes="No other fees documented for this demo account",
        ),
    ]

    critical_for_net = ("observed_spread", "commission", "swap", "slippage")
    by_name = {c["component"]: c for c in comps}
    all_verified = all(by_name[n]["status"] == VERIFIED for n in critical_for_net)

    # Accounting modes
    gross_r_available = True  # always can report gross before costs
    known_cost_adjusted = spread_status in (VERIFIED, PARTIALLY_VERIFIED)
    net_established = all_verified

    # Hypothetical sensitivity scenarios (explicitly labeled)
    hyp_spread = observed_spread_points_median
    scenarios = {
        "observed_spread_only_known": {
            "label": "KNOWN_COST_PARTIAL",
            "spread_points": hyp_spread,
            "commission": UNKNOWN,
            "swap": UNKNOWN,
            "slippage": UNKNOWN,
            "note": "Uses observed median spread only; not complete net",
        },
        "conservative_spread_2x_median": {
            "label": "HYPOTHETICAL_SCENARIO",
            "spread_points": (hyp_spread * 2.0) if hyp_spread is not None else UNKNOWN,
            "commission": UNKNOWN,
            "swap": UNKNOWN,
            "slippage": UNKNOWN,
            "note": "Stress scenario — NOT actual broker cost",
        },
        "adverse_swap_overnight_stress": {
            "label": "HYPOTHETICAL_SCENARIO",
            "swap_long_points_adverse": -644.8,
            "note": "Uses more adverse preserved observation without claiming reconciled fact",
        },
    }

    out = {
        "cost_model_version": COST_MODEL_VERSION,
        "production_approved": False,
        "approval_status": "NOT_APPROVED",
        "components": comps,
        "gross_trade_r_supported": gross_r_available,
        "known_cost_adjusted_r_supported": known_cost_adjusted,
        "conservative_scenario_r_supported": True,
        "net_r_supported": net_established,
        "NET_PROFITABILITY": "ESTABLISHED" if net_established else "NOT_ESTABLISHED",
        "tick_value_usd_per_0_01_lot": VERIFIED_TICK_VALUE,
        "hypothetical_scenarios": scenarios,
        "unknown_components_treated_as_zero": False,
        "sha256": None,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def apply_costs_to_trade_r(
    *,
    gross_r: float,
    risk_price: float,
    spread_price: float | None,
    commission_r: float | None,
    swap_r: float | None,
    slippage_r: float | None,
    cost_model: dict[str, Any],
) -> dict[str, Any]:
    """Convert a single trade's gross R into labeled cost-adjusted figures."""
    if risk_price <= 0:
        raise ValueError("risk_price must be positive")

    spread_r = (spread_price / risk_price) if spread_price is not None else None
    known_adj = gross_r
    known_parts: list[str] = []
    if spread_r is not None and cost_model.get("known_cost_adjusted_r_supported"):
        known_adj = known_adj - spread_r
        known_parts.append("spread")

    # Conservative: apply spread (or 2x if scenario) + any provided numeric stresses as HYPOTHETICAL
    cons = known_adj
    cons_parts = list(known_parts)
    if spread_r is not None:
        cons = cons - spread_r  # extra 1x = 2x total spread stress when spread already applied
        cons_parts.append("extra_spread_stress_1x")
    for name, val in (("commission_hyp", commission_r), ("swap_hyp", swap_r), ("slippage_hyp", slippage_r)):
        if val is not None:
            cons = cons - float(val)
            cons_parts.append(name)

    net = None
    net_status = cost_model.get("NET_PROFITABILITY")
    if net_status == "ESTABLISHED" and all(v is not None for v in (spread_r, commission_r, swap_r, slippage_r)):
        net = gross_r - float(spread_r) - float(commission_r) - float(swap_r) - float(slippage_r)

    return {
        "gross_r": gross_r,
        "known_cost_adjusted_r": known_adj if known_parts else None,
        "known_cost_components_applied": known_parts,
        "conservative_scenario_r": cons,
        "conservative_components": cons_parts,
        "conservative_label": "HYPOTHETICAL_SCENARIO",
        "net_r": net,
        "NET_PROFITABILITY": net_status,
    }
