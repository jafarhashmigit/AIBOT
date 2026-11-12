"""MT5 parity status — no MT5 connection; Phase 33 protocol reused conceptually."""

from __future__ import annotations

from typing import Any

from phase34.constants import MT5_FEATURES_PATH, PHASE33_REPORTS
from phase34.progress import write_json


def report_mt5_parity() -> dict[str, Any]:
    features_exist = MT5_FEATURES_PATH.is_file()
    cols = []
    if features_exist:
        with MT5_FEATURES_PATH.open("r", encoding="utf-8") as f:
            cols = f.readline().strip().split(",")
    has_bid = any(c.startswith("bid_") for c in cols)
    has_ask = any(c.startswith("ask_") for c in cols)
    protocol_path = PHASE33_REPORTS / "mt5_parity_protocol.json"
    report = {
        "status": "MT5_PARITY_PENDING",
        "mt5_connected": False,
        "phase33_protocol_referenced": protocol_path.is_file(),
        "phase33_protocol_path": str(protocol_path).replace("\\", "/") if protocol_path.is_file() else None,
        "approved_mt5_features": {
            "exists": features_exist,
            "has_bid_ohlc": has_bid,
            "has_ask_ohlc": has_ask,
            "has_spread_column": "spread" in cols,
            "has_ohlc": all(c in cols for c in ("open", "high", "low", "close")),
        },
        "verifiable_now": [
            "Presence/absence of bid/ask columns in approved features file",
            "Diagnostic mid-vs-close comparison design (not executed as parity PASS)",
        ],
        "not_verifiable_without_new_mt5_export": [
            "Genuine bid close vs Dukascopy bid close",
            "Genuine ask close vs Dukascopy ask close",
            "Executable spread parity tick-by-tick",
        ],
        "mid_price_vs_mt5_close_is_diagnostic_only": True,
        "mid_price_parity_is_not_bid_ask_parity": True,
        "parity_pass": False,
        "reason_not_pass": "No comparable historical bid/ask observations from MT5 in approved datasets; MT5 not connected.",
    }
    write_json("mt5_parity_status.json", report)
    return report
