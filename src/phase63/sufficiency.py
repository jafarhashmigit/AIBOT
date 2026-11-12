"""Evidence sufficiency — thresholds not lowered."""

from __future__ import annotations

from typing import Any

from phase62.store import ExecutionStore
from phase63.constants import SUFFICIENCY_THRESHOLDS, canonical_json_sha256
from phase63.sessions_util import session_label


def assess_sufficiency(store: ExecutionStore) -> dict[str, Any]:
    thr = dict(SUFFICIENCY_THRESHOLDS)
    deals = [
        r
        for r in store.all_normalized()
        if not r.get("synthetic") and r.get("record_kind") == "DEAL" and r.get("actual_fill_price") is not None
    ]
    # Independent decisions require decision linkage — unavailable → 0
    n_decisions = 0
    days = sorted({str(d.get("fill_timestamp_utc") or "")[:10] for d in deals if d.get("fill_timestamp_utc")})
    sessions = sorted({session_label(str(d.get("fill_timestamp_utc") or "")) for d in deals})
    sessions = [s for s in sessions if s != "UNKNOWN"]

    missing = 0
    slots = 0
    for d in deals:
        for f in ("commission", "side", "volume", "fill_timestamp_utc"):
            slots += 1
            if d.get(f) is None:
                missing += 1
    missing_rate = (missing / slots) if slots else None

    # Multi-deal same order
    by_order: dict[str, int] = {}
    for d in deals:
        oid = str(d.get("order_id") or "")
        by_order[oid] = by_order.get(oid, 0) + 1
    multi = sum(1 for n in by_order.values() if n > 1)

    checks = {
        "independent_decisions": n_decisions >= thr["min_independent_decisions"],
        "actual_fills": len(deals) >= thr["min_actual_fills"],
        "trading_days": len(days) >= thr["min_trading_days"],
        "sessions": len(sessions) >= thr["min_sessions_represented"],
        "missing_rate": missing_rate is not None and missing_rate <= thr["max_missing_record_rate"],
    }
    gaps = {
        "independent_decisions_needed": max(0, thr["min_independent_decisions"] - n_decisions),
        "fills_needed": max(0, thr["min_actual_fills"] - len(deals)),
        "trading_days_needed": max(0, thr["min_trading_days"] - len(days)),
        "sessions_needed": max(0, thr["min_sessions_represented"] - len(sessions)),
    }
    out = {
        "thresholds": thr,
        "thresholds_lowered": False,
        "observed": {
            "n_independent_decisions": n_decisions,
            "n_actual_fills": len(deals),
            "n_trading_days": len(days),
            "sessions": sessions,
            "missing_record_rate": missing_rate,
            "n_multi_deal_orders": multi,
        },
        "checks": checks,
        "sufficient": all(checks.values()),
        "missing_sample_requirements": gaps,
        "note": "Multiple deals from one order/decision are not independent decisions",
        "live_permission": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
