"""Synthetic fixtures. Never presented as trading evidence."""

from __future__ import annotations

from phase6.schemas import (
    CostEstimate,
    MarketState,
    Observation,
    Prediction,
    SideProba,
    Uncertainty,
)
from phase6.constants import COST_ASSUMPTION_VERSION


def observation(timestamp: str = "2026-06-01 10:00:00", **kwargs) -> Observation:
    state = kwargs.pop("market_state", MarketState(1900.0, 1901.0, 1899.0, 1900.5, 100.0, 0.15))
    features = kwargs.pop("features", {"atr14": 2.0, "rsi14": 50.0})
    return Observation(
        timestamp=timestamp,
        market_state=state,
        features=features,
        available_history_end=timestamp,
        **kwargs,
    )


def prediction(*, buy_r: float = 0.0, sell_r: float = 0.0, model_id: str = "no_model") -> Prediction:
    third = 1.0 / 3.0
    return Prediction(
        buy=SideProba(third, third, third),
        sell=SideProba(third, third, third),
        expected_buy_r=buy_r,
        expected_sell_r=sell_r,
        model_id=model_id,
        predictor_version="test",
    )


def uncertainty(buy: float = 0.0, sell: float = 0.0) -> Uncertainty:
    return Uncertainty(method="test", buy=buy, sell=sell)


def costs(usd: float = 0.25) -> CostEstimate:
    return CostEstimate(estimated_usd=usd, version=COST_ASSUMPTION_VERSION)


def record_wait_decision():
    from phase6.decision_engine import DecisionEngine
    from phase6.journal import DecisionJournal
    from phase6.risk_gate import RiskGate
    from phase6.versioning import versions_for

    obs = observation()
    pred = prediction()
    engine = DecisionEngine()
    decision = engine.decide(obs, pred, uncertainty(), costs())
    gate = RiskGate()
    gate_result = gate.evaluate(obs, pred, {"raw_decision": decision.raw_decision})
    versions = versions_for(obs, model_id=pred.model_id)
    journal = DecisionJournal()
    row = journal.record_decision(obs, pred, uncertainty(), costs(), decision, gate_result, versions)
    return journal, row
