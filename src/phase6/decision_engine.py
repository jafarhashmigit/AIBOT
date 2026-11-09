"""Decision engine: prediction + uncertainty + costs → BUY / SELL / WAIT.

Does not train models. Does not read future outcomes or future candles.
Thresholds are frozen Phase 3 protocol constants, not searched in Phase 6.
"""

from __future__ import annotations

from dataclasses import dataclass

from phase6.constants import (
    CONSERVATIVE_K,
    DECISION_ENGINE_VERSION,
    EV_MIN_GAP,
    EV_TAU,
)
from phase6.information_boundary import InformationBoundaryError, assert_decision_time_payload
from phase6.schemas import ACTIONS, CostEstimate, Observation, Prediction, Uncertainty


@dataclass(frozen=True, slots=True)
class DecisionResult:
    raw_decision: str
    reason: str
    conservative_ev_buy: float
    conservative_ev_sell: float
    ev_buy: float
    ev_sell: float
    tau: float
    min_gap: float
    k: float
    decision_engine_version: str = DECISION_ENGINE_VERSION

    def to_mapping(self) -> dict:
        return {
            "raw_decision": self.raw_decision,
            "reason": self.reason,
            "conservative_ev_buy": self.conservative_ev_buy,
            "conservative_ev_sell": self.conservative_ev_sell,
            "ev_buy": self.ev_buy,
            "ev_sell": self.ev_sell,
            "tau": self.tau,
            "min_gap": self.min_gap,
            "k": self.k,
            "decision_engine_version": self.decision_engine_version,
        }


class DecisionEngine:
    def __init__(
        self,
        *,
        tau: float = EV_TAU,
        min_gap: float = EV_MIN_GAP,
        k: float = CONSERVATIVE_K,
        version: str = DECISION_ENGINE_VERSION,
    ) -> None:
        self.tau = float(tau)
        self.min_gap = float(min_gap)
        self.k = float(k)
        self.version = version

    def decide(
        self,
        observation: Observation,
        prediction: Prediction,
        uncertainty: Uncertainty,
        costs: CostEstimate,
    ) -> DecisionResult:
        if not isinstance(observation, Observation):
            raise TypeError("decide() requires an Observation")
        assert_decision_time_payload(observation.to_mapping(), as_of=observation.timestamp)
        # costs are estimates at t, not realized P&L; still reject outcome-like keys
        if costs.estimated_usd < 0:
            raise InformationBoundaryError("estimated cost cannot be negative")

        ev_buy = float(prediction.expected_buy_r)
        ev_sell = float(prediction.expected_sell_r)
        cons_buy = ev_buy - self.k * float(uncertainty.buy)
        cons_sell = ev_sell - self.k * float(uncertainty.sell)

        buy_clears = cons_buy > self.tau
        sell_clears = cons_sell > self.tau
        gap = abs(cons_buy - cons_sell)

        if buy_clears and sell_clears:
            raw, reason = "WAIT", "CONFLICT"
        elif buy_clears and (cons_buy >= cons_sell + self.min_gap):
            raw, reason = "BUY", "conservative_ev_buy_clears"
        elif sell_clears and (cons_sell >= cons_buy + self.min_gap):
            raw, reason = "SELL", "conservative_ev_sell_clears"
        elif buy_clears or sell_clears:
            raw, reason = "WAIT", "near_tie"
        else:
            raw, reason = "WAIT", "conservative_ev_below_tau"

        if gap < self.min_gap and raw in {"BUY", "SELL"}:
            raw, reason = "WAIT", "near_tie"

        if raw not in ACTIONS:
            raise RuntimeError(f"invalid action {raw}")
        return DecisionResult(
            raw_decision=raw,
            reason=reason,
            conservative_ev_buy=cons_buy,
            conservative_ev_sell=cons_sell,
            ev_buy=ev_buy,
            ev_sell=ev_sell,
            tau=self.tau,
            min_gap=self.min_gap,
            k=self.k,
            decision_engine_version=self.version,
        )
