"""Unified decision interface — pluggable policy; default NO_MODEL → WAIT."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from phase54.constants import (
    CHAMPION_STATUS,
    POLICY_VERSION,
    PRODUCTION_FINAL_ACTION,
    SYMBOL,
    TIMEFRAME,
)
from phase54.timeutil import dual_stamp, now_utc_iso


class Policy(Protocol):
    version: str

    def propose(
        self,
        market_state: dict[str, Any],
        features: dict[str, Any],
        model_output: dict[str, Any] | None,
        risk_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Return raw proposed action + optional calibrated fields (may be None)."""


class NullPolicy:
    """Champion NO_MODEL — never invents BUY/SELL or probabilities."""

    version = POLICY_VERSION

    def propose(
        self,
        market_state: dict[str, Any],
        features: dict[str, Any],
        model_output: dict[str, Any] | None,
        risk_state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "action": "WAIT",
            "expected_net_r": None,
            "prob_positive": None,
            "calibrated": False,
            "confidence": None,
            "uncertainty": 1.0,
            "reason_codes": ["NO_MODEL", "NO_VALIDATED_EDGE", "DEFAULT_WAIT"],
        }


def decide(
    market_state: dict[str, Any],
    features: dict[str, Any],
    model_output: dict[str, Any] | None,
    risk_state: dict[str, Any],
    *,
    policy: Policy | None = None,
) -> dict[str, Any]:
    """
    Structured decision. Separates policy proposal from risk finalization.
    Risk layer may convert BUY/SELL → WAIT; never invents direction.
    """
    pol = policy or NullPolicy()
    raw = pol.propose(market_state, features, model_output, risk_state)
    action = str(raw.get("action") or "WAIT")
    if action not in ("BUY", "SELL", "WAIT"):
        action = "WAIT"
        raw = {**raw, "reason_codes": list(raw.get("reason_codes") or []) + ["INVALID_ACTION_FORCED_WAIT"]}

    # Never fabricate calibrated probability / EV
    expected_net_r = raw.get("expected_net_r")
    prob_positive = raw.get("prob_positive")
    calibrated = bool(raw.get("calibrated"))
    if not calibrated:
        expected_net_r = None
        prob_positive = None

    ts = market_state.get("bar_timestamp_utc") or now_utc_iso()
    decision = {
        "decision_id": uuid.uuid4().hex,
        "timestamp_utc": ts,
        "timestamps": dual_stamp(ts),
        "instrument": market_state.get("symbol") or SYMBOL,
        "timeframe": market_state.get("timeframe") or TIMEFRAME,
        "proposed_action": action,
        "action": action,  # may be overridden by risk to WAIT
        "expected_net_r": expected_net_r,
        "prob_positive": prob_positive,
        "calibrated_probabilities": calibrated,
        "risk_estimate": {
            "atr": market_state.get("atr"),
            "spread": market_state.get("spread"),
            "spread_atr": (features or {}).get("E02_spread_atr"),
        },
        "spread": market_state.get("spread"),
        "execution_assumptions": {
            "buy_entry": "ASK",
            "buy_exit": "BID",
            "sell_entry": "BID",
            "sell_exit": "ASK",
            "commission": None,
            "slippage": None,
            "note": "Observed bid/ask only; commission/slippage UNKNOWN",
        },
        "market_regime": (market_state.get("regime") or {}).get("label"),
        "confidence": raw.get("confidence"),
        "uncertainty": raw.get("uncertainty"),
        "reason_codes": list(raw.get("reason_codes") or []),
        "model_policy_version": getattr(pol, "version", POLICY_VERSION),
        "champion": CHAMPION_STATUS,
        "production": PRODUCTION_FINAL_ACTION,
        "data_quality_status": market_state.get("data_quality_status"),
        "observation_id": market_state.get("observation_id"),
        "market_state_id": market_state.get("market_state_id"),
        "created_iso": now_utc_iso(),
        # Optional experimental signal fields (policies may set; NullPolicy leaves None)
        "setup_id": raw.get("setup_id"),
        "entry_reference": raw.get("entry_reference"),
        "stop_loss": raw.get("stop_loss"),
        "take_profit": raw.get("take_profit"),
        "reward_risk": raw.get("reward_risk"),
        "signal_expiry_utc": raw.get("signal_expiry_utc"),
        "signal_expiry_bars": raw.get("signal_expiry_bars"),
        "max_hold_bars": raw.get("max_hold_bars"),
        "invalidation": raw.get("invalidation"),
        "hypothesis_id": raw.get("hypothesis_id"),
        "authorizes_execution": bool(raw.get("authorizes_execution")) if "authorizes_execution" in raw else False,
    }
    return decision
