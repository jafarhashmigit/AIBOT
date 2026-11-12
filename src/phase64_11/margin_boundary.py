"""Margin evidence boundary — separate observed / calculated / estimated."""

from __future__ import annotations

from typing import Any

from phase64_11.constants import (
    CALCULATED,
    ESTIMATED,
    LIVE_ACCOUNT,
    LIVE_MARGIN_MODE,
    LIVE_MARGIN_SO_CALL,
    LIVE_MARGIN_SO_SO,
    STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT,
    USER_REPORTED,
    VERIFIED_CONTRACT_SIZE,
    VERIFIED_CURRENCY,
    VERIFIED_LEVERAGE,
    canonical_json_sha256,
)


def notional(*, price: float, volume: float, contract_size: float = VERIFIED_CONTRACT_SIZE) -> float:
    return float(price) * float(contract_size) * float(volume)


def leverage_estimate(*, price: float, volume: float, leverage: int = VERIFIED_LEVERAGE) -> dict[str, Any]:
    n = notional(price=price, volume=volume)
    return {
        "kind": "C_leverage_based_estimate",
        "evidence_type": CALCULATED,
        "formula": "notional / leverage",
        "notional": n,
        "leverage": leverage,
        "margin_estimate": n / float(leverage),
        "proven_broker_rule": False,
        "usable_as_broker_fact": False,
        "note": "Must not equate to broker required margin unless rules prove the formula for XAUUSDm",
    }


def build_margin_boundary(
    *,
    price: float = 2650.0,
    volume: float = 0.01,
    equity: float = 500.0,
) -> dict[str, Any]:
    lev = leverage_estimate(price=price, volume=volume)
    observed = {
        "kind": "A_broker_observed",
        "evidence_type": LIVE_ACCOUNT,
        "account_margin_used_flat": 0.0,
        "symbol_margin_initial_api": 0.0,
        "symbol_margin_maintenance_api": 0.0,
        "symbol_margin_api_usable": False,
        "margin_so_call": LIVE_MARGIN_SO_CALL,
        "margin_so_so": LIVE_MARGIN_SO_SO,
        "margin_mode": LIVE_MARGIN_MODE,
        "currency_margin": "XAU",
        "currency_profit": VERIFIED_CURRENCY,
        "required_margin_for_new_order": "UNKNOWN",
        "note": "API margin_initial/maintenance 0.0 unusable; flat margin=0 expected; SO levels observed",
    }
    calculated = {
        "kind": "B_calculated_margin",
        "evidence_type": CALCULATED,
        "available": False,
        "reason": "No broker margin rate / order_calc_margin (PROHIBITED) / open position to observe",
    }
    stress = {
        "kind": "D_stress_case_margin",
        "evidence_type": ESTIMATED,
        "method": "scale leverage estimate adversarially",
        "example_2x_leverage_estimate": lev["margin_estimate"] * 2.0,
        "usable_as_broker_fact": False,
    }
    user_reported = {
        "kind": "phase63_user_reported_usd_per_lot",
        "evidence_type": USER_REPORTED,
        "market_buy_usd_per_lot": 199.28,
        "market_sell": None,
        "usable_as_broker_fact": False,
    }

    free = {
        "equity": equity,
        "margin_used": 0.0,
        "free_margin": equity,
        "margin_level_pct": "N/A_flat",
        "free_margin_after_leverage_estimate": equity - float(lev["margin_estimate"]),
        "additional_margin_kind": CALCULATED,
    }

    classification = STRUCTURALLY_UNRESOLVABLE_WITHOUT_ACCOUNT_EVENT
    reasoning = (
        "Exact required margin for a proposed XAUUSDm order is not exposed via permitted RO APIs "
        "(margin_initial/maintenance unusable zeros). order_calc_margin remains PROHIBITED. "
        "Without an actual position/order event (or a future separately approved calc API), "
        "exact broker margin cannot be closed. Leverage and Phase63 figures remain CALCULATED/USER_REPORTED only."
    )

    out = {
        "dimension": "margin",
        "current_state": "INCOMPLETE",
        "MARGIN_MODEL": "INCOMPLETE",
        "layers": {
            "A_broker_observed": observed,
            "B_calculated": calculated,
            "C_leverage_estimate": lev,
            "D_stress": stress,
            "user_reported": user_reported,
        },
        "free_margin_impact": free,
        "conversion_requirements": {
            "margin_currency": "XAU",
            "account_currency": VERIFIED_CURRENCY,
            "status": "UNKNOWN_exact_conversion_path_for_required_margin",
        },
        "maintenance_stopout": {
            "margin_so_call_pct": LIVE_MARGIN_SO_CALL,
            "margin_so_so_pct": LIVE_MARGIN_SO_SO,
            "evidence_type": LIVE_ACCOUNT,
            "note": "Policy thresholds observed; not substitute for required margin",
        },
        "classification": classification,
        "reasoning": reasoning,
        "can_close_without_fill": False,
        "next_evidence": (
            "Genuine open position/order showing account.margin for known volume/price, "
            "OR separate security-approved read-only margin-calc API with audited controls"
        ),
        "order_calc_margin": "PROHIBITED_NOT_INVOKED",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
