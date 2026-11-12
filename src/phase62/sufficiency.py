"""Evidence accumulation vs Phase61 preregistered thresholds."""

from __future__ import annotations

from typing import Any

from phase62.adapters import phase61_thresholds
from phase62.constants import SUFFICIENCY_THRESHOLDS, canonical_json_sha256
from phase62.store import ExecutionStore
from phase62.sessions_util import session_label


def accumulate(store: ExecutionStore, identity: dict[str, Any]) -> dict[str, Any]:
    thr = dict(SUFFICIENCY_THRESHOLDS)
    # Ensure align with phase61
    p61 = phase61_thresholds()
    for k, v in p61.items():
        thr[k] = v

    rows = [r for r in store.all_normalized() if not r.get("synthetic")]
    deals = [r for r in rows if r.get("record_kind") == "DEAL" and r.get("actual_fill_price") is not None]
    orders = {r.get("order_id") for r in rows if r.get("order_id")}
    # Multiple fills per order
    fills_by_order: dict[str, int] = {}
    for d in deals:
        oid = str(d.get("order_id") or "")
        fills_by_order[oid] = fills_by_order.get(oid, 0) + 1
    multi_fill_orders = sum(1 for n in fills_by_order.values() if n > 1)

    days = sorted({str(d.get("fill_timestamp_utc") or "")[:10] for d in deals if d.get("fill_timestamp_utc")})
    sessions = set()
    for d in deals:
        if d.get("fill_timestamp_utc"):
            sessions.add(session_label(str(d["fill_timestamp_utc"])))

    # Independent decisions unknown without decision IDs linked to fills
    n_decisions = 0
    missing_rate = None
    if deals:
        missing_fields = 0
        total_slots = 0
        for d in deals:
            for f in ("commission", "swap", "side", "volume"):
                total_slots += 1
                if d.get(f) is None:
                    missing_fields += 1
        missing_rate = missing_fields / total_slots if total_slots else None

    q = store.quarantine_rows()
    account_ok = bool(identity.get("core_identity_verified"))
    instrument_vals = {r.get("symbol") for r in deals if r.get("symbol")}
    instrument_ok = len(instrument_vals) <= 1 and identity.get("exact_broker_symbol") not in (None, "UNKNOWN")

    checks = {
        "independent_decisions": n_decisions >= thr["min_independent_decisions"],
        "actual_fills": len(deals) >= thr["min_actual_fills"],
        "trading_days": len(days) >= thr["min_trading_days"],
        "sessions": len(sessions) >= thr["min_sessions_represented"],
        "missing_rate": missing_rate is not None and missing_rate <= thr["max_missing_record_rate"],
        "account_identity": account_ok,
        "instrument_consistency": instrument_ok or len(deals) == 0,
    }

    out = {
        "preregistered_thresholds": thr,
        "thresholds_lowered_after_outcomes": False,
        "observed": {
            "n_independent_decisions": n_decisions,
            "n_orders": len(orders),
            "n_deals_fills": len(deals),
            "n_multi_fill_orders": multi_fill_orders,
            "n_trading_days": len(days),
            "sessions_represented": sorted(sessions),
            "missing_record_rate": missing_rate,
            "n_quarantined": len(q),
            "symbols_seen": sorted(instrument_vals),
        },
        "checks": checks,
        "sufficient_operational_gate": all(checks.values()),
        "sufficient_statistical_validation": False,
        "claim_blocked_if_identity_or_costs_unknown": True,
        "distinction": "accumulation ≠ statistical validation; demo ≠ live",
        "confidence_interval_limitations": "Not claimed without adequate independent linked decisions",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
