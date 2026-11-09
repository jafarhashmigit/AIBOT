"""Forward RiskGate adapter. Reuses Phase 6 apply_gate; does not call evaluate().

Full Phase 6 evaluate() parity: NOT_PROVEN (Phase 6 refuses post-cutoff Observations).
RiskGate apply_gate parity: established against pre-cutoff evaluate()+apply_gate table.
"""

from __future__ import annotations

from phase6.constants import CHAMPION_ID, RISK_GATE_VERSION
from phase6.risk_gate import GateResult, RiskGate, apply_gate
from phase12c.constants import ADAPTER_VERSION, FULL_EVALUATE_PARITY

ACTIONS = frozenset({"BUY", "SELL", "WAIT"})


class ForwardGateAdapterError(ValueError):
    pass


class ForwardGateAdapter:
    """Versioned forward-only gate adapter.

    Reused from Phase 6 (unchanged):
      - RiskGate() configuration defaults (wait_only, champion_id, version)
      - GateResult dataclass
      - apply_gate(raw_decision, gate_result)

    Independently implemented in Phase 12C:
      - Branch selection that mirrors the wait_only / no_model path inside
        RiskGate.evaluate WITHOUT calling evaluate() or constructing a Phase 6
        Observation for post-cutoff timestamps.
      - Fail-closed WAIT for missing/invalid inputs.

    Does not weaken RiskGate. Does not create BUY/SELL from WAIT.
    """

    def __init__(self) -> None:
        self.version = ADAPTER_VERSION
        self.gate = RiskGate()
        if not self.gate.wait_only or self.gate.champion_id != CHAMPION_ID:
            raise ForwardGateAdapterError("HARD FAILURE: Phase 6 RiskGate defaults changed")
        if self.gate.version != RISK_GATE_VERSION:
            raise ForwardGateAdapterError("HARD FAILURE: RiskGate version changed")
        self.full_evaluate_parity = FULL_EVALUATE_PARITY

    def frozen_config(self) -> dict:
        return {
            "adapter_version": self.version,
            "wait_only": self.gate.wait_only,
            "champion_id": self.gate.champion_id,
            "risk_gate_version": self.gate.version,
            "full_evaluate_parity": self.full_evaluate_parity,
            "reused": ["RiskGate.__init__", "GateResult", "apply_gate"],
            "not_called": ["RiskGate.evaluate", "DecisionEngine.decide", "Observation"],
            "independently_implemented": [
                "wait_only/no_model GateResult branch selection for forward timestamps",
                "fail-closed input validation before apply_gate",
            ],
        }

    def build_gate_result(self, raw_action: str) -> GateResult:
        if raw_action not in ACTIONS:
            raise ForwardGateAdapterError(f"invalid raw_action {raw_action}")
        constraints = {
            "wait_only": self.gate.wait_only,
            "champion_id": self.gate.champion_id,
            "raw_decision": raw_action,
            "adapter_version": self.version,
            "evaluate_called": False,
        }
        if raw_action == "WAIT":
            return GateResult("ALLOW", True, "raw_wait", constraints)
        if self.gate.wait_only or self.gate.champion_id == "no_model":
            return GateResult("BLOCK", False, "wait_only_no_champion", constraints)
        # Champion is frozen no_model; executable ALLOW path is unreachable and refused.
        raise ForwardGateAdapterError("executable ALLOW path refused under frozen no_model champion")

    def apply(self, raw_action: str) -> dict:
        result = self.build_gate_result(raw_action)
        final = apply_gate(raw_action, result)
        if final not in ACTIONS:
            raise ForwardGateAdapterError("apply_gate returned invalid action")
        # Safety: ALLOW must never invent a direction from WAIT.
        if raw_action == "WAIT" and final != "WAIT":
            raise ForwardGateAdapterError("gate must not create BUY/SELL from WAIT")
        return {
            "raw_action": raw_action,
            "gate_status": result.status,
            "gate_allowed": result.allowed,
            "gate_reason": result.reason,
            "final_action": final,
            "evaluate_called": False,
            "apply_gate_reused": True,
            "full_evaluate_parity": self.full_evaluate_parity,
            "adapter_version": self.version,
        }
