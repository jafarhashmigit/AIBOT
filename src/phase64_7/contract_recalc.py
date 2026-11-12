"""Contract & risk recalculation using verified live fields only."""

from __future__ import annotations

from typing import Any

from phase64_6.contract_integrity import (
    margin_estimate,
    position_notional,
    price_to_ticks,
    round_volume_to_step,
    stop_loss_monetary_risk,
    ticks_to_money,
)
from phase64_6.risk_policy import UNAPPROVED, propose_demo_risk_policy
from phase64_7.constants import INCOMPLETE, UNKNOWN, canonical_json_sha256


def recalculate_from_probe(probe: dict[str, Any]) -> dict[str, Any]:
    if probe.get("status") != "LIVE_PROBE_OK":
        return {
            "status": "NOT_RUN",
            "reason": probe.get("status"),
            "contract_calculation_completeness": INCOMPLETE,
            "risk_policy_approval_status": UNAPPROVED,
            "pass": False,
        }

    sym = (probe.get("raw") or {}).get("symbol") or {}
    acct = (probe.get("raw") or {}).get("account") or {}
    tick_size = sym.get("tick_size")
    tick_value = sym.get("tick_value")
    contract_size = sym.get("contract_size")
    volume_min = sym.get("volume_min")
    volume_step = sym.get("volume_step")
    volume_max = sym.get("volume_max")
    bid = sym.get("bid")

    missing = [
        k
        for k, v in {
            "tick_size": tick_size,
            "tick_value": tick_value,
            "contract_size": contract_size,
            "volume_min": volume_min,
            "volume_step": volume_step,
        }.items()
        if v in (None, "", UNKNOWN)
    ]

    examples = []
    # Validate tick conversion
    examples.append({"name": "price_to_ticks_1point", "result": price_to_ticks(0.001, tick_size=tick_size)})
    examples.append({"name": "ticks_to_money_10ticks_0.01lot", "result": ticks_to_money(10, tick_value=tick_value, volume=0.01)})
    examples.append(
        {
            "name": "notional_0.01",
            "result": position_notional(price=float(bid or 0), volume=0.01, contract_size=contract_size),
        }
    )
    # Margin: user-reported buy margin rate may exist but not independently verified via API
    examples.append(
        {
            "name": "margin_estimate",
            "result": margin_estimate(volume=0.01, margin_per_lot=UNKNOWN),
            "note": "API margin_initial UNKNOWN/zero — cannot claim exact margin",
        }
    )
    # Example SL: 1.0 price units (~1000 ticks if tick_size=0.001)
    examples.append(
        {
            "name": "sl_risk_0.01lot_1.0_price",
            "result": stop_loss_monetary_risk(
                entry=float(bid or 0),
                stop=float(bid or 0) - 1.0,
                volume=0.01,
                tick_size=tick_size,
                tick_value=tick_value,
            ),
        }
    )
    examples.append(
        {
            "name": "volume_step_round",
            "result": round_volume_to_step(0.01, volume_step=volume_step, volume_min=volume_min, volume_max=volume_max),
        }
    )

    remaining_cost_unknowns = [
        "commission_schedule",
        "actual_slippage",
        "execution_latency",
        "initial_margin_api",
        "maintenance_margin_api",
        "trading_sessions_complete",
    ]

    sl = examples[-2]["result"]
    calc_complete = len(missing) == 0 and sl.get("status") == "OK"

    risk = propose_demo_risk_policy(
        account_balance=acct.get("balance"),
        account_currency=acct.get("currency"),
    )

    out = {
        "status": "CALCULATED",
        "verified_inputs": {
            "tick_size": tick_size,
            "tick_value": tick_value,
            "tick_value_profit": sym.get("tick_value_profit"),
            "tick_value_loss": sym.get("tick_value_loss"),
            "contract_size": contract_size,
            "volume_min": volume_min,
            "volume_step": volume_step,
            "volume_max": volume_max,
            "account_currency": acct.get("currency"),
            "account_leverage": acct.get("leverage"),
        },
        "missing_critical_inputs": missing,
        "examples": examples,
        "remaining_unknown_cost_inputs": remaining_cost_unknowns,
        "contract_calculation_completeness": "COMPLETE" if calc_complete else INCOMPLETE,
        "risk_policy_proposal": risk,
        "risk_policy_approval_status": UNAPPROVED,
        "risk_limits_approved_this_phase": False,
        "pass": calc_complete and risk["approval_status"] == UNAPPROVED,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k not in ("sha256", "examples", "risk_policy_proposal")})
    return out
