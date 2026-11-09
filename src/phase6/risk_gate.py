"""Risk gate: ALLOW or BLOCK. Never changes direction. Never learns from future outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field

from phase6.constants import (
    CHAMPION_ID,
    MAX_COST_TO_SL_FRACTION,
    RESEARCH_CUTOFF,
    RISK_GATE_VERSION,
)
from phase6.information_boundary import InformationBoundaryError
from phase6.schemas import Observation, Prediction


@dataclass(frozen=True, slots=True)
class GateResult:
    status: str  # ALLOW | BLOCK
    allowed: bool
    reason: str
    constraints: dict = field(default_factory=dict)

    def to_mapping(self) -> dict:
        return {
            "status": self.status,
            "allowed": self.allowed,
            "reason": self.reason,
            "constraints": dict(self.constraints),
        }


class RiskGate:
    """Can only convert BUY/SELL into WAIT. Cannot create a directional signal."""

    def __init__(
        self,
        *,
        wait_only: bool = True,
        max_cost_to_sl: float = MAX_COST_TO_SL_FRACTION,
        version: str = RISK_GATE_VERSION,
        champion_id: str = CHAMPION_ID,
    ) -> None:
        self.wait_only = bool(wait_only)
        self.max_cost_to_sl = float(max_cost_to_sl)
        self.version = version
        self.champion_id = champion_id

    def evaluate(
        self,
        observation: Observation,
        prediction: Prediction,
        decision_context: dict,
    ) -> GateResult:
        if not isinstance(observation, Observation):
            raise TypeError("evaluate() requires an Observation")
        if str(observation.timestamp) > RESEARCH_CUTOFF:
            raise InformationBoundaryError("risk gate refuses post-cutoff timestamps")

        raw = str(decision_context.get("raw_decision", "WAIT"))
        constraints = {
            "wait_only": self.wait_only,
            "champion_id": self.champion_id,
            "max_cost_to_sl": self.max_cost_to_sl,
            "raw_decision": raw,
        }

        if raw == "WAIT":
            return GateResult("ALLOW", True, "raw_wait", constraints)

        if self.wait_only or self.champion_id == "no_model":
            return GateResult(
                "BLOCK",
                False,
                "wait_only_no_champion",
                constraints,
            )

        sl_distance = observation.feature_map().get("atr14")
        if sl_distance is not None and sl_distance > 0:
            frac = observation.estimated_cost_usd / sl_distance
            constraints["cost_to_sl"] = frac
            if frac > self.max_cost_to_sl:
                return GateResult("BLOCK", False, "cost_exceeds_sl_fraction", constraints)

        if observation.market_state.tick_volume < 0:
            return GateResult("BLOCK", False, "invalid_market_state", constraints)

        # Gate does not inspect prediction quality to flip side; it only blocks.
        _ = prediction
        return GateResult("ALLOW", True, "passed", constraints)


def apply_gate(raw_decision: str, gate: GateResult) -> str:
    """Blocked BUY/SELL become WAIT. WAIT cannot become BUY/SELL."""
    if raw_decision == "WAIT":
        return "WAIT"
    if not gate.allowed or gate.status == "BLOCK":
        return "WAIT"
    return raw_decision
