"""Classify execution-model realism dimensions."""

from __future__ import annotations

from typing import Any


def classify_execution_realism(
    *,
    trade_cost_ok: bool,
    label_ok: bool,
    bid_ask_verified: bool,
) -> dict[str, Any]:
    dimensions = {
        "cost_arithmetic": {
            "status": "VERIFIED" if trade_cost_ok else "FAILED",
            "note": "gross - costs = net; net_r = net_pnl / initial_risk",
        },
        "historical_spread": {
            "status": "ASSUMPTION_BASED",
            "note": "MT5 min-within-bar spread floored at 15 points; not verified vs historical bid/ask",
        },
        "entry_exit_fills": {
            "status": "ASSUMPTION_BASED",
            "note": "Idealized barrier fills at exact TP/SL inside bar high/low; no tick path",
        },
        "slippage": {
            "status": "ASSUMPTION_BASED",
            "note": "Fixed $0.05/side extra cost stands in for commission+slippage",
        },
        "market_impact": {
            "status": "INSUFFICIENT_EVIDENCE",
            "note": "Not modeled",
        },
        "label_barrier_contract": {
            "status": "VERIFIED" if label_ok else "FAILED",
            "note": "Independent reconstruction vs stored labels/outcomes",
        },
    }

    if bid_ask_verified:
        overall = "HISTORICAL_BID_ASK_VERIFIED"
    elif trade_cost_ok and label_ok:
        overall = "ASSUMPTION_BASED"
    elif trade_cost_ok or label_ok:
        overall = "PARTIALLY_VERIFIED"
    else:
        overall = "INSUFFICIENT_EVIDENCE"

    return {
        "classification": overall,
        "dimensions": dimensions,
        "bid_ask_verified": bid_ask_verified,
        "note": (
            "Correct cost arithmetic ≠ realistic historical spread/fills. "
            "Without verified bid/ask parity, execution remains assumption-based."
        ),
    }
