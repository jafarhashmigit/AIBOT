"""Independent monetary risk calculations — never invent commission; preserve swap conflict."""

from __future__ import annotations

from typing import Any

from phase64_9.constants import (
    RISK_CALC_VERSION,
    RISK_INCOMPLETE,
    SWAP_LONG_PHASE63,
    SWAP_LONG_PHASE64_7,
    UNKNOWN,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_TICK_SIZE,
    VERIFIED_TICK_VALUE,
    canonical_json_sha256,
)


def round_volume_to_step(volume: float, step: float, vmin: float, vmax: float) -> dict[str, Any]:
    if step <= 0:
        return {"ok": False, "reason": "invalid_step", "rounded": UNKNOWN}
    # Floor to step alignment
    n = int(volume / step + 1e-12)
    rounded = round(n * step, 10)
    if rounded < vmin - 1e-12:
        return {"ok": False, "reason": "below_min", "rounded": rounded}
    if rounded > vmax + 1e-12:
        return {"ok": False, "reason": "above_max", "rounded": rounded}
    # Check exact alignment of original
    aligned = abs(volume - rounded) < 1e-9 or abs((volume / step) - round(volume / step)) < 1e-9
    return {"ok": True, "rounded": rounded, "aligned": aligned, "original": volume}


def ticks_between(price_a: float, price_b: float, tick_size: float) -> float | str:
    if tick_size in (None, 0) or tick_size == UNKNOWN:
        return UNKNOWN
    return abs(float(price_a) - float(price_b)) / float(tick_size)


def monetary_risk_from_sl(
    *,
    direction: str,
    entry: float,
    sl: float,
    volume: float,
    tick_size: float = VERIFIED_TICK_SIZE,
    tick_value: float = VERIFIED_TICK_VALUE,
    contract_size: float = VERIFIED_CONTRACT_SIZE,
) -> dict[str, Any]:
    """Risk = ticks_to_SL * tick_value * (volume / 0.01) for Exness-style tick_value@0.01 lot.
    Using verified tick_value as monetary value per tick per 0.01 lot (Phase64.7 live).
    """
    d = direction.upper()
    if d == "BUY":
        if sl >= entry:
            return {"ok": False, "reason": "buy_sl_not_below_entry", "monetary_risk": UNKNOWN}
    elif d == "SELL":
        if sl <= entry:
            return {"ok": False, "reason": "sell_sl_not_above_entry", "monetary_risk": UNKNOWN}
    else:
        return {"ok": False, "reason": "invalid_direction", "monetary_risk": UNKNOWN}

    ticks = ticks_between(entry, sl, tick_size)
    if ticks is UNKNOWN:
        return {"ok": False, "reason": "tick_size_unknown", "monetary_risk": UNKNOWN, "status": RISK_INCOMPLETE}

    # tick_value is per 0.01 lot on this broker (verified)
    lots_units = float(volume) / 0.01
    risk = float(ticks) * float(tick_value) * lots_units
    return {
        "ok": True,
        "direction": d,
        "entry": entry,
        "sl": sl,
        "volume": volume,
        "ticks_to_sl": ticks,
        "tick_size": tick_size,
        "tick_value": tick_value,
        "contract_size": contract_size,
        "monetary_risk": risk,
        "status": "COMPUTED",
    }


def estimate_total_downside(
    *,
    sl_risk: dict[str, Any],
    spread_points: Any = None,
    tick_size: float = VERIFIED_TICK_SIZE,
    tick_value: float = VERIFIED_TICK_VALUE,
    volume: float = 0.01,
    commission: Any = None,
    swap: Any = None,
    accept_unknown_commission: bool = False,
) -> dict[str, Any]:
    if not sl_risk.get("ok"):
        return {
            "status": RISK_INCOMPLETE,
            "reason": sl_risk.get("reason") or "sl_risk_failed",
            "total_estimated_downside": UNKNOWN,
            "components": {"sl_risk": sl_risk},
        }

    components: dict[str, Any] = {"sl_monetary_risk": sl_risk["monetary_risk"]}

    # Spread impact (one-way entry cost approximation)
    if spread_points in (None, UNKNOWN):
        components["spread_cost"] = UNKNOWN
    else:
        try:
            ticks = float(spread_points)  # points ≈ ticks when tick_size=point
            components["spread_cost"] = ticks * float(tick_value) * (float(volume) / 0.01)
        except (TypeError, ValueError):
            components["spread_cost"] = UNKNOWN

    if commission is None or commission is UNKNOWN:
        components["commission"] = UNKNOWN
        if not accept_unknown_commission:
            return {
                "status": RISK_INCOMPLETE,
                "reason": "commission_unknown",
                "total_estimated_downside": UNKNOWN,
                "components": components,
                "swap_conflict_note": {
                    "phase63": SWAP_LONG_PHASE63,
                    "phase64_7": SWAP_LONG_PHASE64_7,
                    "interchangeable": False,
                },
            }
    else:
        components["commission"] = float(commission)

    # Swap: do not use conflicting values interchangeably; overnight only when applicable
    if swap is None or swap is UNKNOWN:
        components["swap"] = UNKNOWN
        components["swap_included_in_total"] = False
    else:
        components["swap"] = float(swap)
        components["swap_included_in_total"] = True

    nums = []
    for k in ("sl_monetary_risk", "spread_cost", "commission"):
        v = components.get(k)
        if v is UNKNOWN:
            return {
                "status": RISK_INCOMPLETE,
                "reason": f"unknown_component:{k}",
                "total_estimated_downside": UNKNOWN,
                "components": components,
            }
        nums.append(float(v))
    if components.get("swap_included_in_total"):
        nums.append(float(components["swap"]))

    total = sum(nums)
    out = {
        "status": "COMPUTED",
        "total_estimated_downside": total,
        "components": components,
        "risk_calc_version": RISK_CALC_VERSION,
        "swap_conflict_preserved": {
            "phase63_swap_long": SWAP_LONG_PHASE63,
            "phase64_7_swap_long": SWAP_LONG_PHASE64_7,
            "used_as_interchangeable": False,
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def run_risk_calc_tests() -> dict[str, Any]:
    cases = []

    buy = monetary_risk_from_sl(direction="BUY", entry=2650.0, sl=2649.0, volume=0.01)
    # 1.0 / 0.001 = 1000 ticks * 0.1 * 1 = 100
    cases.append({"name": "buy_sl_risk", "pass": buy.get("ok") and abs(buy["monetary_risk"] - 100.0) < 1e-6, "detail": buy})

    sell = monetary_risk_from_sl(direction="SELL", entry=2650.0, sl=2651.0, volume=0.01)
    cases.append({"name": "sell_sl_risk", "pass": sell.get("ok") and abs(sell["monetary_risk"] - 100.0) < 1e-6, "detail": sell})

    bad_buy = monetary_risk_from_sl(direction="BUY", entry=2650.0, sl=2651.0, volume=0.01)
    cases.append({"name": "buy_invalid_sl", "pass": not bad_buy.get("ok")})

    vol = round_volume_to_step(0.013, 0.01, 0.01, 200.0)
    cases.append({"name": "volume_rounding", "pass": vol["ok"] and vol["rounded"] == 0.01})

    ticks = ticks_between(2650.0, 2649.0, 0.001)
    cases.append({"name": "tick_conversion", "pass": ticks == 1000.0})

    cases.append({"name": "monetary_risk", "pass": buy.get("ok")})

    downside = estimate_total_downside(
        sl_risk=buy, spread_points=30, commission=-0.06, volume=0.01
    )
    cases.append(
        {
            "name": "spread_and_commission_impact",
            "pass": downside["status"] == "COMPUTED" and downside["total_estimated_downside"] > 100.0,
            "detail": downside,
        }
    )

    unknown_c = estimate_total_downside(sl_risk=buy, spread_points=30, commission=None)
    cases.append({"name": "unknown_commission_incomplete", "pass": unknown_c["status"] == RISK_INCOMPLETE})

    # Swap conflict not interchangeable
    cases.append(
        {
            "name": "swap_conflict_not_interchangeable",
            "pass": SWAP_LONG_PHASE63 != SWAP_LONG_PHASE64_7
            and unknown_c.get("swap_conflict_note", {}).get("interchangeable") is False,
        }
    )

    out = {
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c["pass"]),
        "cases": cases,
        "suite_pass": all(c["pass"] for c in cases),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
