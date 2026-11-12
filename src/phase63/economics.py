"""Execution economics ledger — unknowns stay UNKNOWN."""

from __future__ import annotations

from typing import Any

from phase62.store import ExecutionStore
from phase63.constants import canonical_json_sha256
from phase63.sessions_util import session_label


def build_economics_ledger(store: ExecutionStore, metadata: dict[str, Any]) -> dict[str, Any]:
    rows = [r for r in store.all_normalized() if not r.get("synthetic")]
    deals = [r for r in rows if r.get("record_kind") == "DEAL" and r.get("actual_fill_price") is not None]
    orders = [r for r in rows if r.get("record_kind") == "ORDER"]

    ledgers = []
    missing_commission = 0
    missing_swap = 0
    missing_fee = 0
    for d in deals:
        commission = d.get("commission")
        swap = d.get("swap")
        fee = d.get("fee")
        if commission is None:
            missing_commission += 1
        if swap is None:
            missing_swap += 1
        if fee is None:
            missing_fee += 1
        entry = {
            "deal_id": d.get("deal_id"),
            "order_id": d.get("order_id"),
            "symbol": d.get("symbol"),
            "side": d.get("side"),
            "volume": d.get("volume"),
            "actual_execution_price": d.get("actual_fill_price"),
            "requested_price": d.get("requested_price"),
            "observed_spread": "UNKNOWN",  # not in deal export alone
            "decision_reference_price": "UNKNOWN",
            "slippage": "UNKNOWN",  # no valid independent reference
            "slippage_label": "NOT_ACTUAL_WITHOUT_REFERENCE",
            "commission": commission if commission is not None else "UNKNOWN",
            "swap": swap if swap is not None else "UNKNOWN",
            "fee": fee if fee is not None else "UNKNOWN",
            "realized_profit_loss": d.get("profit") if d.get("profit") is not None else "UNKNOWN",
            "execution_timestamp": d.get("fill_timestamp_utc"),
            "latency": "UNKNOWN",
            "session": session_label(str(d.get("fill_timestamp_utc") or "")),
            "missing_or_unverifiable": (
                [x for x, v in (("commission", commission), ("swap", swap), ("fee", fee)) if v is None]
                + ["decision_reference_price", "observed_spread", "slippage", "latency"]
            ),
        }
        ledgers.append(entry)

    out = {
        "n_deals": len(deals),
        "n_orders": len(orders),
        "n_ledger_rows": len(ledgers),
        "missing_commission_n": missing_commission,
        "missing_swap_n": missing_swap,
        "missing_fee_n": missing_fee,
        "missing_treated_as_zero": False,
        "quote_estimates_called_actual_slippage": False,
        "latency_claimed_without_timestamps": False,
        "broker_fill_behavior_from_simulation": False,
        "account_type_user_reported": (metadata.get("values") or {}).get("account_type"),
        "tick_value_user_reported": (metadata.get("values") or {}).get("tick_value"),
        "sample_rows": ledgers[:20],
        "rules": [
            "Unknown remains UNKNOWN",
            "Missing fees never zero",
            "Quote estimates ≠ actual broker slippage",
            "Multiple deals ≠ independent decisions without decision linkage",
        ],
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
