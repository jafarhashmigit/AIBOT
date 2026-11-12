"""Derive outcome evidence from closed trade — no fabrication."""

from __future__ import annotations

from typing import Any

from phase57_1.constants import JOURNAL_SCHEMA_VERSION, deterministic_experience_id


def build_exit_payload(closed: dict[str, Any], *, decision: dict[str, Any] | None, obs: dict[str, Any] | None) -> dict[str, Any]:
    side = closed.get("side")
    exec_side = "BID" if side == "BUY" else "ASK" if side == "SELL" else None
    return {
        "position_id": closed.get("position_id"),
        "decision_id": closed.get("decision_id") or (decision or {}).get("decision_id"),
        "observation_id": closed.get("observation_id") or (obs or {}).get("observation_id"),
        "market_state_id": closed.get("market_state_id") or (obs or {}).get("market_state_id"),
        "symbol": closed.get("symbol"),
        "timeframe": closed.get("timeframe"),
        "side": side,
        "entry_timestamp": closed.get("entry_timestamp"),
        "entry_fill": closed.get("entry_fill"),
        "entry_bid": closed.get("entry_bid"),
        "entry_ask": closed.get("entry_ask"),
        "entry_spread": closed.get("entry_spread"),
        "entry_bar": closed.get("entry_bar"),
        "entry_idx": closed.get("entry_idx"),
        "stop_loss": closed.get("stop_loss"),
        "take_profit": closed.get("take_profit"),
        "atr_at_entry": closed.get("atr_at_entry"),
        "exit_timestamp": closed.get("exit_timestamp"),
        "exit_reason": closed.get("exit_reason"),
        "exit_fill": closed.get("exit_fill"),
        "exit_bid": closed.get("exit_bid"),
        "exit_ask": closed.get("exit_ask"),
        "exit_idx": closed.get("exit_idx"),
        "exit_bar": closed.get("exit_bar"),
        "execution_side_exit": exec_side,
        "gross_pnl": closed.get("gross_pnl"),
        "net_pnl": closed.get("net_pnl"),
        "net_r": closed.get("net_r"),
        "commission": closed.get("commission"),
        "slippage": closed.get("slippage"),
        "decision_snapshot": {
            "timestamp_utc": (decision or {}).get("timestamp_utc") or closed.get("entry_timestamp"),
            "action": (decision or {}).get("action") or side,
            "reason_codes": (decision or {}).get("reason_codes"),
            "model_policy_version": (decision or {}).get("model_policy_version"),
        },
        "schema_version": JOURNAL_SCHEMA_VERSION,
    }


def derive_outcome(exit_payload: dict[str, Any]) -> dict[str, Any]:
    """Outcome is a projection of committed exit evidence — never invents fills."""
    required = ("position_id", "side", "exit_reason", "exit_fill", "entry_fill")
    missing = [k for k in required if exit_payload.get(k) is None]
    if missing:
        return {"ok": False, "error": "incomplete_exit_evidence", "missing": missing}
    return {
        "ok": True,
        "position_id": exit_payload["position_id"],
        "side": exit_payload["side"],
        "exit_reason": exit_payload["exit_reason"],
        "entry_fill": exit_payload["entry_fill"],
        "exit_fill": exit_payload["exit_fill"],
        "exit_bid": exit_payload.get("exit_bid"),
        "exit_ask": exit_payload.get("exit_ask"),
        "execution_side_exit": exit_payload.get("execution_side_exit"),
        "gross_pnl": exit_payload.get("gross_pnl"),
        "net_pnl": exit_payload.get("net_pnl"),
        "net_r": exit_payload.get("net_r"),
        "commission": exit_payload.get("commission"),
        "slippage": exit_payload.get("slippage"),
    }


def experience_from_exit(
    *,
    txn_id: str,
    exit_payload: dict[str, Any],
    outcome: dict[str, Any],
    source: str = "AGENT_SHADOW",
    horizon_bars: int = 12,
) -> dict[str, Any]:
    from phase50.constants import EXPERIENCE_SCHEMA_VERSION, LEARNER_VERSION, MARKET_STATE_VERSION
    from phase54.timeutil import now_utc_iso

    dec = exit_payload.get("decision_snapshot") or {}
    exp_id = deterministic_experience_id(txn_id, source)
    return {
        "experience_id": exp_id,
        "source": source,
        "decision_timestamp_utc": str(dec.get("timestamp_utc") or exit_payload.get("entry_timestamp")),
        "market_state_id": str(exit_payload.get("market_state_id") or "unknown"),
        "action": str(dec.get("action") or exit_payload.get("side")),
        "decision_context": {
            "decision_id": exit_payload.get("decision_id"),
            "position_id": exit_payload.get("position_id"),
            "txn_id": txn_id,
            "exit_reason": exit_payload.get("exit_reason"),
            "reason_codes": dec.get("reason_codes"),
            "phase57_1_journal": True,
        },
        "expected_value": None,
        "actual_costed_outcome_net_r": float(outcome.get("net_r") or 0.0),
        "outcome_horizon_bars": int(horizon_bars),
        "outcome_timestamp_utc": str(exit_payload.get("exit_timestamp")),
        "regime_context": {},
        "feature_representation_version": MARKET_STATE_VERSION,
        "policy_version": str(dec.get("model_policy_version") or "unknown"),
        "learner_version": LEARNER_VERSION,
        "creation_timestamp_utc": now_utc_iso(),
        "experience_schema_version": EXPERIENCE_SCHEMA_VERSION,
        "confidence": None,
        "decision_reason": ",".join(dec.get("reason_codes") or []) or str(exit_payload.get("exit_reason")),
    }
