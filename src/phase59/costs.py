"""Execution cost component classification — unknown stays unknown."""

from __future__ import annotations

from typing import Any

from phase46.cost_scenarios import COST_SCENARIO_REGISTRY
from phase59.constants import canonical_json_sha256


def build_cost_classification() -> dict[str, Any]:
    components = [
        {
            "component": "bid_ask_spread",
            "classification": "DIRECTLY_MEASURED",
            "evidence": "Historical tick bid/ask when present; embedded in BUY ask→bid / SELL bid→ask fills",
            "value_invented": False,
        },
        {
            "component": "commission",
            "classification": "UNKNOWN",
            "evidence": "No broker commission schedule in archives; OBSERVED_BIDASK_ONLY sets commission=None",
            "value_invented": False,
            "must_not_treat_as_zero": True,
        },
        {
            "component": "slippage",
            "classification": "UNKNOWN",
            "evidence": "No measured slippage distribution vs intended price; research proxies labeled only",
            "value_invented": False,
            "must_not_treat_as_zero": True,
        },
        {
            "component": "execution_delay",
            "classification": "UNKNOWN",
            "evidence": "Historical replay uses first/last tick in bar — not measured order latency",
            "value_invented": False,
        },
        {
            "component": "stop_loss_execution",
            "classification": "HISTORICALLY_OBSERVABLE",
            "evidence": "Paper path uses first tick hitting SL on bid (BUY) / ask (SELL); gap-through not broker-filled",
            "value_invented": False,
        },
        {
            "component": "take_profit_execution",
            "classification": "HISTORICALLY_OBSERVABLE",
            "evidence": "Symmetric to SL on opposite side of book in paper monitor",
            "value_invented": False,
        },
        {
            "component": "gap_risk",
            "classification": "PARTIALLY_OBSERVABLE",
            "evidence": "Inter-bar gaps visible in M5; weekend gaps partially visible; fill realism unknown",
            "value_invented": False,
        },
        {
            "component": "adverse_selection_during_execution",
            "classification": "UNKNOWN",
            "evidence": "Not identifiable from demo tick archives alone",
            "value_invented": False,
        },
    ]
    scenarios = {
        sid: {
            "id": sid,
            "live_broker_truth": sc.get("live_broker_truth"),
            "commission_usd_per_side": sc.get("commission_usd_per_side"),
            "slippage_usd_per_side": sc.get("slippage_usd_per_side"),
            "spread_widen_mult": sc.get("spread_widen_mult"),
            "description": sc.get("description"),
            "provenance": sc.get("cost_provenance") or ("OBSERVED" if sid == "OBSERVED_BIDASK_ONLY" else "HYPOTHETICAL_STRESS"),
        }
        for sid, sc in COST_SCENARIO_REGISTRY.items()
    }
    out = {
        "components": components,
        "scenarios_from_phase46": scenarios,
        "gross_vs_net_rule": (
            "Gross = price path PnL from bid/ask fills. "
            "Observed net under OBSERVED_BIDASK_ONLY equals gross (spread embedded). "
            "Commission/slippage remain UNKNOWN and are NOT set to zero."
        ),
        "demo_caveat": "MetaQuotes-Demo bid/ask ≠ live broker execution economics",
    }
    out["cost_sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "cost_sha256"})
    return out
