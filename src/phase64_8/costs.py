"""Commission / swap / execution-cost handling — never invent missing values."""

from __future__ import annotations

from typing import Any

from phase64_8.constants import UNKNOWN, canonical_json_sha256


def cost_field(value: Any) -> Any:
    """Return broker-reported number or UNKNOWN — never coerce missing to 0."""
    if value is None:
        return UNKNOWN
    if value is UNKNOWN:
        return UNKNOWN
    try:
        return float(value)
    except (TypeError, ValueError):
        return UNKNOWN


def separate_costs(
    *,
    commission: Any = None,
    swap: Any = None,
    fee: Any = None,
    spread: Any = None,
    execution_price: Any = None,
    reference_price: Any = None,
    other_charges: Any = None,
) -> dict[str, Any]:
    commission_v = cost_field(commission)
    swap_v = cost_field(swap)
    fee_v = cost_field(fee)
    spread_v = cost_field(spread)
    other_v = cost_field(other_charges)

    deviation: Any = UNKNOWN
    if execution_price is not None and reference_price is not None:
        try:
            deviation = float(execution_price) - float(reference_price)
        except (TypeError, ValueError):
            deviation = UNKNOWN

    components = {
        "spread": spread_v,
        "execution_price_deviation": deviation,
        "commission": commission_v,
        "swap": swap_v,
        "fee": fee_v,
        "other_broker_charges": other_v,
    }
    # Synthetic total only when every component is a concrete number
    nums = []
    for k, v in components.items():
        if k == "execution_price_deviation":
            continue  # deviation is not a cash charge by itself
        if v is UNKNOWN:
            nums = None
            break
        nums.append(float(v))
    synthetic = sum(nums) if nums is not None else UNKNOWN

    out = {
        **components,
        "synthetic_total_cost": synthetic,
        "synthetic_total_defined": synthetic is not UNKNOWN,
        "note": "Do not collapse components unless every component is explicitly defined",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
