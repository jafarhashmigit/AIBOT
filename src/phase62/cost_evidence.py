"""Demo cost evidence status — separate published vs actual deal fields."""

from __future__ import annotations

from typing import Any

from phase62.constants import canonical_json_sha256
from phase62.store import ExecutionStore


def demo_cost_evidence_status(store: ExecutionStore, identity: dict[str, Any]) -> dict[str, Any]:
    rows = [r for r in store.all_normalized() if not r.get("synthetic")]
    commissions = [r.get("commission") for r in rows]
    known_c = [c for c in commissions if c is not None]
    swaps = [r.get("swap") for r in rows]
    known_s = [s for s in swaps if s is not None]
    fills = [r for r in rows if r.get("record_kind") == "DEAL" and r.get("actual_fill_price") is not None]

    out = {
        "published_broker_commission_schedule": {
            "status": "INVESTIGATION_REFERENCE_ONLY",
            "activated": False,
            "note": "Must not derive missing commission from published Exness figures",
        },
        "account_specific_verified_commission_schedule": {
            "status": "UNKNOWN"
            if identity.get("fields", {}).get("applicable_commission_schedule", {}).get("status") != "VERIFIED"
            else "VERIFIED",
            "value": identity.get("fields", {}).get("applicable_commission_schedule", {}).get("value"),
        },
        "actual_demo_deal_commission": {
            "n_deals": len(fills),
            "n_with_commission_field": len(known_c),
            "n_null_commission": sum(1 for c in commissions if c is None),
            "status": "PRESENT" if known_c else ("EMPTY_STORE" if not rows else "ALL_NULL_OR_MISSING"),
            "does_not_prove_live_commission": True,
        },
        "historical_spread": {"status": "SEPARATE_DOMAIN", "mixed_into_demo_store": False},
        "actual_fill_slippage": {"status": "UNKNOWN", "note": "Requires decision benchmark linkage"},
        "swap": {
            "n_with_swap_field": len(known_s),
            "status": "PRESENT" if known_s else ("EMPTY_STORE" if not rows else "ALL_NULL_OR_MISSING"),
        },
        "other_verified_fees": {"status": "UNKNOWN"},
        "fully_adjusted_performance_allowed": False,
        "reason_blocked": "Account identity and/or material cost components UNKNOWN; demo≠live",
        "zero_fill_of_unknowns": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
