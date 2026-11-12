"""Transparent per-trade cost ledger — unknowns stay unknown; no false totals."""

from __future__ import annotations

from typing import Any

from phase61.constants import canonical_json_sha256


def component(name: str, value: float | None, *, unit: str, source: str, status: str) -> dict[str, Any]:
    return {"name": name, "value": value, "unit": unit, "source": source, "status": status}


def build_trade_ledger(
    *,
    gross_price_move: float | None,
    spread_cost: float | None,
    spread_already_in_fill: bool,
    commission: float | None,
    commission_status: str,
    slippage: float | None,
    slippage_status: str,
    swap: float | None,
    swap_status: str,
    other_verified_fees: float | None = None,
    other_status: str = "NONE",
) -> dict[str, Any]:
    comps = [
        component(
            "SPREAD_COST",
            None if spread_already_in_fill else spread_cost,
            unit="price_or_account_ccy",
            source="bid_ask_or_schedule",
            status=("EMBEDDED_IN_FILL_NOT_ADDED_AGAIN" if spread_already_in_fill else ("KNOWN" if spread_cost is not None else "UNKNOWN")),
        ),
        component("COMMISSION", commission, unit="account_ccy", source="account_schedule_or_deal", status=commission_status),
        component("SLIPPAGE", slippage, unit="price_or_account_ccy", source="fill_vs_benchmark", status=slippage_status),
        component("SWAP", swap, unit="account_ccy", source="overnight_financing", status=swap_status),
        component(
            "OTHER_VERIFIED_FEES",
            other_verified_fees,
            unit="account_ccy",
            source="verified_fee_schedule",
            status=other_status if other_verified_fees is not None else "NONE",
        ),
    ]

    material_unknown = any(
        c["status"] in ("UNKNOWN",) and c["name"] in ("COMMISSION", "SLIPPAGE", "SWAP", "SPREAD_COST")
        for c in comps
        if not (c["name"] == "SPREAD_COST" and c["status"] == "EMBEDDED_IN_FILL_NOT_ADDED_AGAIN")
    )
    # SWAP may be zero for intraday — still UNKNOWN if not verified for overnight trades
    known_sum = 0.0
    can_sum = True
    for c in comps:
        if c["status"] in ("EMBEDDED_IN_FILL_NOT_ADDED_AGAIN", "NONE"):
            continue
        if c["status"] == "UNKNOWN" or c["value"] is None:
            if c["name"] in ("COMMISSION", "SLIPPAGE"):
                can_sum = False
            elif c["name"] == "SWAP" and c["status"] == "UNKNOWN":
                can_sum = False
            elif c["name"] == "SPREAD_COST" and c["status"] == "UNKNOWN":
                can_sum = False
            continue
        known_sum += float(c["value"])

    total = known_sum if can_sum and not material_unknown else None

    return {
        "gross_price_movement": gross_price_move,
        "spread_adjusted_performance": None,  # caller may supply separately
        "components": comps,
        "TOTAL_COST": total,
        "total_complete": total is not None,
        "false_complete_total_prevented": total is None and material_unknown,
        "double_count_spread_prevented": spread_already_in_fill,
        "formula": "TOTAL_COST = SPREAD_COST + COMMISSION + SLIPPAGE + SWAP + OTHER_VERIFIED_FEES (known terms only)",
        "metrics_separated": {
            "gross_price_movement": True,
            "spread_adjusted": True,
            "fully_cost_adjusted": total is not None,
        },
    }


def audit_ledger_examples() -> dict[str, Any]:
    unknown = build_trade_ledger(
        gross_price_move=1.2,
        spread_cost=0.17,
        spread_already_in_fill=True,
        commission=None,
        commission_status="UNKNOWN",
        slippage=None,
        slippage_status="UNKNOWN",
        swap=None,
        swap_status="UNKNOWN",
    )
    # Verified commission-free Pro-like + measured slippage 0 + no overnight
    complete = build_trade_ledger(
        gross_price_move=1.2,
        spread_cost=0.17,
        spread_already_in_fill=True,
        commission=0.0,
        commission_status="VERIFIED",
        slippage=0.05,
        slippage_status="MEASURED",
        swap=0.0,
        swap_status="VERIFIED_INTRADAY_ZERO",
    )
    # Partial close duplication check
    partial_a = build_trade_ledger(
        gross_price_move=0.5,
        spread_cost=None,
        spread_already_in_fill=True,
        commission=0.035,  # portion of round-turn
        commission_status="VERIFIED",
        slippage=0.01,
        slippage_status="MEASURED",
        swap=0.0,
        swap_status="VERIFIED_INTRADAY_ZERO",
    )
    out = {
        "unknown_case_total_complete": unknown["total_complete"],
        "unknown_case_total": unknown["TOTAL_COST"],
        "complete_case_total_complete": complete["total_complete"],
        "complete_case_total": complete["TOTAL_COST"],
        "partial_close_example": partial_a,
        "examples": {"unknown": unknown, "complete": complete},
        "pass_unknown_refuses_total": unknown["TOTAL_COST"] is None and unknown["false_complete_total_prevented"],
        "pass_complete_has_total": complete["TOTAL_COST"] is not None,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
