"""Margin model — distinguish CALCULATED_ESTIMATE from BROKER_OBSERVED."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import (
    BROKER_OBSERVED,
    CALCULATED_ESTIMATE,
    MARGIN_MODEL_VERSION,
    PHASE63_MARGIN_BUY_USD_PER_LOT,
    UNKNOWN,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_LEVERAGE,
    canonical_json_sha256,
)


def notional_exposure(*, price: float, volume: float, contract_size: float = VERIFIED_CONTRACT_SIZE) -> float:
    """Notional in quote/profit terms for XAUUSDm: price * contract_size * volume."""
    return float(price) * float(contract_size) * float(volume)


def leverage_margin_estimate(
    *,
    price: float,
    volume: float,
    leverage: int = VERIFIED_LEVERAGE,
    contract_size: float = VERIFIED_CONTRACT_SIZE,
) -> dict[str, Any]:
    """
    Simple notional/leverage estimate. Does NOT prove exact broker margin for metals
    (margin currency XAU; broker may use proprietary rates).
    """
    notional = notional_exposure(price=price, volume=volume, contract_size=contract_size)
    if leverage <= 0:
        return {"status": CALCULATED_ESTIMATE, "margin": UNKNOWN, "reason": "invalid_leverage"}
    est = notional / float(leverage)
    return {
        "kind": CALCULATED_ESTIMATE,
        "method": "notional_div_leverage",
        "notional": notional,
        "leverage": leverage,
        "margin_estimate_usd": est,
        "note": "Leverage alone does not prove exact broker margin requirements for XAUUSDm",
        "usable_as_broker_fact": False,
    }


def phase63_user_reported_margin_estimate(*, volume: float = 0.01) -> dict[str, Any]:
    """Preserve Phase63 user-reported buy USD/lot — not live API verified."""
    per_lot = PHASE63_MARGIN_BUY_USD_PER_LOT
    return {
        "kind": CALCULATED_ESTIMATE,
        "method": "phase63_user_reported_market_buy_usd_per_lot",
        "usd_per_lot": per_lot,
        "volume": volume,
        "margin_estimate_usd": per_lot * (float(volume) / 1.0),
        "provenance": "USER_REPORTED_PHASE63",
        "sell_rate": None,
        "usable_as_broker_fact": False,
        "note": "initial/maintenance rates were TRUNCATED in Phase63 export",
    }


def broker_observed_margin(
    *,
    account_margin: Any = None,
    symbol_margin_initial: Any = None,
    symbol_margin_maintenance: Any = None,
) -> dict[str, Any]:
    """
    Live account.margin is observed for open exposure (often 0 when flat).
    symbol margin_initial/maintenance of 0.0 on this broker are treated as UNKNOWN (unusable).
    """
    init = symbol_margin_initial
    maint = symbol_margin_maintenance
    # Zero API margin fields on metals are not trustworthy required-margin facts
    if init in (0, 0.0):
        init = UNKNOWN
    if maint in (0, 0.0):
        maint = UNKNOWN
    if init is None:
        init = UNKNOWN
    if maint is None:
        maint = UNKNOWN

    return {
        "kind": BROKER_OBSERVED,
        "account_margin_used": account_margin if account_margin is not None else UNKNOWN,
        "symbol_margin_initial": init,
        "symbol_margin_maintenance": maint,
        "usable_required_margin": init not in (UNKNOWN, None) and maint not in (UNKNOWN, None),
        "note": "API margin_initial/maintenance 0.0 treated as UNKNOWN; flat account.margin=0 is expected",
    }


def free_margin_impact(
    *,
    equity: float,
    margin_used: float,
    additional_margin_estimate: float | None = None,
) -> dict[str, Any]:
    free = float(equity) - float(margin_used)
    after = UNKNOWN
    if additional_margin_estimate is not None:
        after = free - float(additional_margin_estimate)
    level = UNKNOWN
    if margin_used and float(margin_used) > 0:
        level = (float(equity) / float(margin_used)) * 100.0
    return {
        "equity": equity,
        "margin_used": margin_used,
        "free_margin": free,
        "free_margin_after_estimate": after,
        "margin_level_pct": level,
        "additional_margin_kind": CALCULATED_ESTIMATE if additional_margin_estimate is not None else None,
    }


def build_margin_model(
    *,
    price: float = 2650.0,
    volume: float = 0.01,
    equity: float = 500.0,
    account_margin: float = 0.0,
    symbol_margin_initial: Any = 0.0,
    symbol_margin_maintenance: Any = 0.0,
) -> dict[str, Any]:
    lev = leverage_margin_estimate(price=price, volume=volume)
    p63 = phase63_user_reported_margin_estimate(volume=volume)
    obs = broker_observed_margin(
        account_margin=account_margin,
        symbol_margin_initial=symbol_margin_initial,
        symbol_margin_maintenance=symbol_margin_maintenance,
    )
    impact = free_margin_impact(
        equity=equity,
        margin_used=float(account_margin or 0.0),
        additional_margin_estimate=lev.get("margin_estimate_usd"),
    )
    incomplete = not obs["usable_required_margin"]
    out = {
        "margin_model_version": MARGIN_MODEL_VERSION,
        "MARGIN_MODEL": "INCOMPLETE" if incomplete else "COMPLETE",
        "notional": notional_exposure(price=price, volume=volume),
        "leverage_estimate": lev,
        "phase63_user_reported_estimate": p63,
        "broker_observed": obs,
        "free_margin_impact": impact,
        "blocks_execution_when_safety_depends_on_exact_margin": incomplete,
        "order_calc_margin_api": "PROHIBITED_NOT_INVOKED",
        "distinction": {
            CALCULATED_ESTIMATE: "notional/leverage and Phase63 user-reported rates",
            BROKER_OBSERVED: "account.margin / symbol margin fields when trustworthy",
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
