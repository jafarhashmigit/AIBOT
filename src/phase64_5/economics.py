"""Broker-evidence cost ledger — INCOMPLETE when required fields missing."""

from __future__ import annotations

from typing import Any

from phase64_5.constants import UNKNOWN, canonical_json_sha256

INCOMPLETE = "INCOMPLETE"


def deal_cost_record(deal: dict[str, Any]) -> dict[str, Any]:
    comps = {
        "executed_volume": deal.get("volume"),
        "fill_price": deal.get("price"),
        "commission": deal.get("commission"),
        "swap": deal.get("swap"),
        "fee": deal.get("fee"),
        "realized_profit": deal.get("profit"),
    }
    # Never replace missing with zero
    missing = [k for k, v in comps.items() if v is None]
    # Essential for complete economics: volume, price, and at least commission known (even if 0)
    essential_missing = [k for k in ("executed_volume", "fill_price", "commission") if comps.get(k) is None]
    status = INCOMPLETE if essential_missing else "COMPLETE_DEAL_FRAGMENT"
    # Position-level net still incomplete without full entry/exit pair
    return {
        "broker_deal_id": deal.get("broker_deal_id"),
        "components": comps,
        "missing_components": missing,
        "essential_missing": essential_missing,
        "total_execution_economics": INCOMPLETE if essential_missing else status,
        "position_level_complete": False,
        "published_schedules_used": False,
        "historical_proxies_used": False,
        "evidence_label": deal.get("evidence_label"),
        "synthetic": deal.get("synthetic"),
    }


def build_cost_ledger(events: list[dict[str, Any]]) -> dict[str, Any]:
    deals = [e for e in events if e.get("record_kind") == "BROKER_DEAL"]
    records = [deal_cost_record(d) for d in deals]
    n_complete = sum(1 for r in records if r["total_execution_economics"] != INCOMPLETE)
    n_incomplete = sum(1 for r in records if r["total_execution_economics"] == INCOMPLETE)
    out = {
        "n_deal_cost_records": len(records),
        "n_complete_fragments": n_complete,
        "n_incomplete": n_incomplete,
        "records": records,
        "aggregate_net_execution_economics": INCOMPLETE,
        "reason_aggregate_incomplete": "position_entry_exit_pairing_and/or_missing_costs",
        "zero_substitution": False,
        "genuine_only_counts": {
            "n": sum(1 for r in records if not r.get("synthetic")),
            "incomplete": sum(1 for r in records if not r.get("synthetic") and r["total_execution_economics"] == INCOMPLETE),
        },
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256" and k != "records"})
    return out
