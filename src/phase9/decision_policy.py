"""Frozen Phase 9 rule on learner predicted R, then Phase 6 RiskGate."""

from __future__ import annotations

from dataclasses import dataclass

from phase6.decision_engine import DecisionEngine, DecisionResult
from phase6.risk_gate import RiskGate, apply_gate
from phase6.schemas import CostEstimate, Observation, Prediction, Uncertainty


@dataclass(frozen=True)
class PolicyResult:
    raw_decision: str
    final_decision: str
    reason: str
    source: str
    pred_buy: float | None
    pred_sell: float | None
    gate_status: str


def experience_rule(pred_buy: float, pred_sell: float) -> tuple[str, str]:
    if pred_buy > 0 and pred_buy > pred_sell:
        return "BUY", "learner_buy_positive_and_greater"
    if pred_sell > 0 and pred_sell > pred_buy:
        return "SELL", "learner_sell_positive_and_greater"
    return "WAIT", "learner_no_side_clears"


def apply_frozen_gate(raw: str, obs: Observation, pred: Prediction) -> tuple[str, str]:
    gate = RiskGate()  # wait_only, no_model — unchanged
    result = gate.evaluate(obs, pred, {"raw_decision": raw})
    return apply_gate(raw, result), result.status


def decide(
    obs: Observation,
    rf_prediction: Prediction,
    uncertainty: Uncertainty,
    costs: CostEstimate,
    learner_buy: float | None,
    learner_sell: float | None,
) -> PolicyResult:
    if learner_buy is None or learner_sell is None:
        engine = DecisionEngine()
        raw_res: DecisionResult = engine.decide(obs, rf_prediction, uncertainty, costs)
        final, status = apply_frozen_gate(raw_res.raw_decision, obs, rf_prediction)
        reason = raw_res.reason if final == raw_res.raw_decision else f"gate_block:{status}"
        return PolicyResult(raw_res.raw_decision, final, reason, "cold_start_phase6_engine",
                            None, None, status)
    raw, reason = experience_rule(learner_buy, learner_sell)
    final, status = apply_frozen_gate(raw, obs, rf_prediction)
    if final != raw:
        reason = f"gate_block:{status}"
    return PolicyResult(raw, final, reason, "experience_ridge", learner_buy, learner_sell, status)
