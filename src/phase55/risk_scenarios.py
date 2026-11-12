"""WAIT and risk-rejection scenarios using Phase54 RiskManager + real/fixture observations."""

from __future__ import annotations

from typing import Any

from phase54.decision import decide
from phase54.risk import RiskManager
from phase55.constants import ENGINEERING_TAG
from phase55.engineering_policy import EngineeringTestPolicy


def _gate(action: str, market_state: dict[str, Any], risk: RiskManager) -> dict[str, Any]:
    pol = EngineeringTestPolicy([action])
    decision = decide(market_state, market_state.get("features") or {}, None, risk.snapshot(), policy=pol)
    gate = risk.evaluate(decision, market_state)
    decision["action"] = gate["final_action"]
    decision["risk_gate"] = gate
    decision["reason_codes"] = list(decision.get("reason_codes") or []) + list(gate.get("reasons") or []) + [
        ENGINEERING_TAG
    ]
    return {"decision": decision, "gate": gate}


def run_risk_rejection_battery(base_obs: dict[str, Any]) -> dict[str, Any]:
    """base_obs must be an accepted observation from real or synthetic data."""
    results = {}

    # WAIT — no position path (caller verifies); gate allows WAIT
    r = RiskManager()
    results["wait_allowed"] = _gate("WAIT", base_obs, r)

    # Excessive spread
    r = RiskManager({"max_spread_price": 0.0001})
    results["spread_block"] = _gate("BUY", {**base_obs, "spread": 1.0}, r)

    # Invalid ATR / stop
    r = RiskManager()
    results["invalid_stop"] = _gate("BUY", {**base_obs, "atr": None}, r)

    # Daily loss
    r = RiskManager({"max_daily_loss_r": 0.5})
    day = str(base_obs.get("day") or "")[:10]
    r.daily_realized_r[day] = -1.0
    results["daily_loss_block"] = _gate("SELL", base_obs, r)

    # Max drawdown
    r = RiskManager({"max_drawdown_r": 0.5})
    r.peak_equity_r = 2.0
    r.equity_r = 1.0  # dd = 1.0 >= 0.5
    results["drawdown_block"] = _gate("BUY", base_obs, r)

    # Max open positions
    r = RiskManager({"max_simultaneous_positions": 1})
    r.register_open("p1", {"market_state_id": "other", "side": "BUY", "symbol": base_obs.get("symbol")})
    results["max_positions_block"] = _gate("BUY", {**base_obs, "market_state_id": "new"}, r)

    # Duplicate
    r = RiskManager()
    r.register_open("p1", {"market_state_id": base_obs.get("market_state_id"), "side": "BUY", "symbol": base_obs.get("symbol")})
    results["duplicate_block"] = _gate("BUY", base_obs, r)

    # Circuit breaker
    r = RiskManager({"circuit_breaker_errors": 1})
    r.note_error()
    results["circuit_breaker"] = _gate("SELL", base_obs, r)

    # Summarize expected WAIT finals
    summary = {}
    for k, v in results.items():
        summary[k] = {
            "final_action": v["gate"]["final_action"],
            "allowed": v["gate"]["allowed"],
            "reasons": v["gate"]["reasons"],
        }
    return {"cases": results, "summary": summary}
