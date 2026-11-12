"""Machine-readable execution-cost model — never collapse UNKNOWN to zero."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import (
    CONFLICTING,
    COST_MODEL_VERSION,
    ESTIMATED,
    UNKNOWN,
    UNKNOWN_FOR_EXECUTION,
    VERIFIED,
    canonical_json_sha256,
)


def component(
    name: str,
    *,
    status: str,
    value: Any = UNKNOWN,
    unit: str | None = None,
    provenance: str | None = None,
    usable_for_deterministic_execution: bool | None = None,
    notes: str = "",
) -> dict[str, Any]:
    usable = usable_for_deterministic_execution
    if usable is None:
        usable = status == VERIFIED
    return {
        "component": name,
        "status": status,
        "value": value,
        "unit": unit,
        "provenance": provenance,
        "usable_for_deterministic_execution": usable,
        "notes": notes,
    }


def build_cost_model(
    *,
    spread_points: Any = None,
    spread_status: str = UNKNOWN,
    slippage: Any = UNKNOWN,
    slippage_status: str = UNKNOWN,
    commission: Any = UNKNOWN,
    commission_status: str = UNKNOWN,
    swap: Any = UNKNOWN,
    swap_status: str = UNKNOWN_FOR_EXECUTION,
    other_charges: Any = UNKNOWN,
    other_status: str = UNKNOWN,
    financing: Any = UNKNOWN,
    financing_status: str = UNKNOWN,
) -> dict[str, Any]:
    comps = [
        component(
            "spread",
            status=spread_status,
            value=spread_points if spread_points is not None else UNKNOWN,
            unit="points",
            provenance="LIVE_MT5_tick_bid_ask" if spread_status == VERIFIED else None,
            notes="Observed bid/ask distance; floating; snapshot only",
        ),
        component(
            "execution_price_deviation_slippage",
            status=slippage_status,
            value=slippage,
            unit="price_units",
            notes="Requires fill vs reference; no trade fills → UNKNOWN",
        ),
        component(
            "commission",
            status=commission_status,
            value=commission,
            unit="account_currency_per_deal_or_lot",
            notes="Do not assume generic Exness schedule applies to this account",
        ),
        component(
            "swap",
            status=swap_status,
            value=swap,
            unit="points_per_lot_per_day",
            notes="Conflicting observations preserved; not interchangeable",
        ),
        component(
            "other_broker_charges",
            status=other_status,
            value=other_charges,
            notes="Fees/adjustments not observed on trade deals",
        ),
        component(
            "financing_related_costs",
            status=financing_status,
            value=financing,
            notes="Financing beyond swap not separately verified",
        ),
    ]

    verified = [c for c in comps if c["status"] == VERIFIED]
    unknown = [c for c in comps if c["status"] in (UNKNOWN, UNKNOWN_FOR_EXECUTION)]
    conflicting = [c for c in comps if c["status"] == CONFLICTING]
    estimated = [c for c in comps if c["status"] == ESTIMATED]

    # Deterministic total only if every execution-critical component is VERIFIED
    critical = ("spread", "commission", "swap")  # slippage post-trade; others secondary
    critical_ok = all(
        next(c for c in comps if c["component"] == n)["status"] == VERIFIED for n in critical
    )
    synthetic_total: Any = UNKNOWN
    if critical_ok and all(c["usable_for_deterministic_execution"] for c in comps if c["component"] in critical):
        # Still do not invent — only sum numeric verified criticals if present
        nums = []
        for n in critical:
            v = next(c for c in comps if c["component"] == n)["value"]
            if v in (None, UNKNOWN):
                nums = None
                break
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                nums = None
                break
        synthetic_total = sum(nums) if nums is not None else UNKNOWN

    out = {
        "cost_model_version": COST_MODEL_VERSION,
        "components": comps,
        "counts": {
            "VERIFIED": len(verified),
            "UNKNOWN": len(unknown),
            "CONFLICTING": len(conflicting),
            "ESTIMATED": len(estimated),
        },
        "deterministic_execution_cost_complete": critical_ok and synthetic_total is not UNKNOWN,
        "synthetic_total_critical_components": synthetic_total,
        "rule": "Only VERIFIED values may be used for deterministic execution-cost calculations",
        "estimated_for_stress_only": True,
        "never_collapse_unknown_to_zero": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
