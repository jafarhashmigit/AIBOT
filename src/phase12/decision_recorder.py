"""Shadow decision journal. Champion no_model → WAIT. Not a paper trade."""

from __future__ import annotations

from phase6.constants import CHAMPION_ID
from phase6.risk_gate import GateResult, apply_gate
from phase12.validation import SOURCE_FORWARD, frozen_risk_gate, ShadowError

PAPER_TRADE = False


def propose_action(*, champion_id: str | None = None) -> dict:
    """No approved production model. Do not use the Phase 9 experimental learner."""
    champ = champion_id if champion_id is not None else CHAMPION_ID
    if champ != "no_model":
        raise ShadowError("Phase 12 refuses to promote an experimental model")
    return {
        "model_id": None,
        "model_status": "NO_MODEL",
        "raw_action": "WAIT",
        "decision_reason": "NO_APPROVED_MODEL",
    }


def apply_frozen_gate(raw_action: str) -> tuple[str, str]:
    """Apply Phase 6 apply_gate() using the same WAIT-only branches evaluate() uses.

    Does not call RiskGate.evaluate() on post-cutoff Observations — that method
    refuses those timestamps by design and is unchanged. This is frozen-policy
    table application, not a claim that evaluate() supports forward bars.
    """
    if raw_action not in {"BUY", "SELL", "WAIT"}:
        raise ShadowError(f"unknown raw_action {raw_action}")
    gate = frozen_risk_gate()
    constraints = {
        "wait_only": gate.wait_only,
        "champion_id": gate.champion_id,
        "raw_decision": raw_action,
    }
    if raw_action == "WAIT":
        result = GateResult("ALLOW", True, "raw_wait", constraints)
    elif gate.wait_only or gate.champion_id == "no_model":
        result = GateResult("BLOCK", False, "wait_only_no_champion", constraints)
    else:
        raise ShadowError("unexpected executable raw action under frozen champion")
    final = apply_gate(raw_action, result)
    return result.status, final


def record_shadow_decision(observation: dict) -> dict:
    proposal = propose_action()
    gate_status, final = apply_frozen_gate(proposal["raw_action"])
    if final not in {"BUY", "SELL", "WAIT"}:
        raise ShadowError("invalid final_action")
    return {
        "decision_id": observation["decision_id"],
        "observation_id": observation["observation_id"],
        "source_type": SOURCE_FORWARD,
        "decision_timestamp_utc": observation["bar_close_timestamp_utc"],
        "symbol": observation["symbol"],
        "timeframe": observation["timeframe"],
        "model_id": "",
        "model_status": proposal["model_status"],
        "raw_action": proposal["raw_action"],
        "risk_gate_result": gate_status,
        "final_action": final,
        "decision_reason": proposal["decision_reason"],
        "outcome_status": "pending",
        "is_paper_trade": False,
        "is_paper_execution": False,
        "note": "FORWARD_SHADOW WAIT is not AGENT_PAPER and not a trade",
    }
