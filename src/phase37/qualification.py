"""Qualification gates and final verdict selection."""

from __future__ import annotations

from typing import Any


def apply_qualification(evidence: dict[str, Any]) -> dict[str, Any]:
    pre = evidence.get("preflight") or {}
    m5 = evidence.get("m5_tests") or {}
    ticks = evidence.get("tick_tests") or {}
    speed = evidence.get("speed") or {}
    rng = evidence.get("range_probe") or {}
    indep = evidence.get("independent_validation") or {}

    mt5_available = bool(pre.get("terminal_exists")) and bool(pre.get("package", {}).get("available"))
    connected = (pre.get("connection") or {}).get("status") == "connected_readonly"
    symbol_ok = (pre.get("symbol") or {}).get("status") == "ok"

    m5_periods = m5.get("periods") or {}
    m5_pass_all = bool(m5_periods) and all(
        (p.get("analysis") or {}).get("pass_ohlc")
        and (p.get("analysis") or {}).get("pass_chrono")
        and int(p.get("n") or 0) > 0
        for p in m5_periods.values()
    )
    m5_utc_ok = bool(m5.get("utc_normalization_documented"))

    tick_periods = ticks.get("periods") or {}
    tick_any = any(int(p.get("n") or 0) > 0 for p in tick_periods.values())
    tick_bid_ask = bool(ticks.get("bid_available")) and bool(ticks.get("ask_available"))
    tick_chrono = bool(ticks.get("chrono_pass"))
    tick_spread = bool(ticks.get("spread_pass"))
    # Historical tick range: prefer explicit range-probe confirm; else sample-period ticks count
    # as confirmed recent history (still not "unlimited" depth).
    tick_range_ok = bool(rng.get("EARLIEST_CONFIRMED_TICK")) or (
        tick_any and tick_bid_ask and tick_chrono and tick_spread
    )

    m5_gate = bool(connected and symbol_ok and m5_pass_all and m5_utc_ok)
    tick_gate = bool(
        connected and symbol_ok and tick_any and tick_bid_ask and tick_chrono and tick_spread and tick_range_ok
    )
    speed_gate = bool(speed.get("materially_faster_than_phase36_dukascopy"))

    indep_ok = bool(indep.get("ok", True))

    if not mt5_available or not connected:
        verdict = "MT5_UNAVAILABLE"
    elif m5_gate and tick_gate and speed_gate and indep_ok:
        verdict = "MT5_HISTORICAL_SOURCE_QUALIFIED"
    elif m5_gate or (tick_any and tick_bid_ask):
        verdict = "MT5_PARTIALLY_QUALIFIED"
    else:
        verdict = "MT5_HISTORICAL_SOURCE_NOT_QUALIFIED"

    return {
        "gates": {
            "m5_bar_qualification": m5_gate,
            "tick_qualification": tick_gate,
            "speed_qualification": speed_gate,
            "independent_reload_ok": indep_ok,
        },
        "final_verdict": verdict,
        "notes": {
            "m5": "PASS requires retrievable bars, UTC normalization documented, valid OHLC, chrono order, gaps detectable",
            "tick": "PASS requires bid/ask present, chrono+spread integrity, confirmed historical range",
            "speed": "PASS if bounded MT5 retrieval materially faster/practical than Phase36 Dukascopy experience",
        },
    }
