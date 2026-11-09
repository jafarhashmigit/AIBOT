"""Research-only chronological replay. No shuffling. No lookahead."""

from __future__ import annotations

from dataclasses import dataclass

from phase6.constants import COST_ASSUMPTION_VERSION
from phase6.decision_engine import DecisionEngine
from phase6.information_boundary import InformationBoundaryError, parse_stamp
from phase6.journal import DecisionJournal
from phase6.predictor import Predictor
from phase6.risk_gate import RiskGate
from phase6.schemas import CostEstimate, MarketState, Observation, Uncertainty
from phase6.versioning import observation_hash, versions_for


@dataclass(frozen=True, slots=True)
class HistoricalBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: float
    spread: float | None = None
    features: tuple[tuple[str, float], ...] = ()


class ObservationBuilder:
    """Builds an Observation from bars with timestamp <= t only."""

    def __init__(self, bars: list[HistoricalBar], *, model_id: str = "no_model") -> None:
        self.bars = list(bars)
        self.model_id = model_id
        stamps = [b.timestamp for b in self.bars]
        if stamps != sorted(stamps):
            raise InformationBoundaryError("historical bars are not chronological")
        if len(stamps) != len(set(stamps)):
            raise InformationBoundaryError("duplicate historical timestamps")

    def prefix(self, timestamp: str) -> list[HistoricalBar]:
        return [b for b in self.bars if b.timestamp <= timestamp]

    def build(self, timestamp: str) -> Observation:
        prefix = self.prefix(timestamp)
        if not prefix:
            raise InformationBoundaryError(f"no history at or before {timestamp}")
        if prefix[-1].timestamp != timestamp:
            raise InformationBoundaryError(f"no closed bar at {timestamp}")
        future = [b for b in self.bars if b.timestamp > timestamp]
        if any(b.timestamp <= timestamp for b in future):
            raise InformationBoundaryError("lookahead in prefix split")
        bar = prefix[-1]
        obs = Observation(
            timestamp=timestamp,
            market_state=MarketState(
                open=bar.open, high=bar.high, low=bar.low,
                close=bar.close, tick_volume=bar.tick_volume, spread=bar.spread,
            ),
            features=bar.features,
            model_id=self.model_id,
            estimated_cost_usd=0.25 if bar.spread is None else max(bar.spread, 0.15) + 0.10,
            available_history_end=timestamp,
        )
        payload = obs.to_mapping()
        payload["data_hash"] = observation_hash(obs)
        return Observation.from_mapping(payload)


class HistoricalReplay:
    def __init__(
        self,
        bars: list[HistoricalBar],
        predictor: Predictor,
        engine: DecisionEngine,
        gate: RiskGate,
        *,
        uncertainty: Uncertainty | None = None,
    ) -> None:
        self.builder = ObservationBuilder(bars, model_id=predictor.metadata().get("model_id", "no_model"))
        self.predictor = predictor
        self.engine = engine
        self.gate = gate
        self.uncertainty = uncertainty or Uncertainty(method="none", buy=0.0, sell=0.0)
        self.journal = DecisionJournal()
        self.processed: list[str] = []

    def run(self, timestamps: list[str] | None = None) -> DecisionJournal:
        stamps = timestamps if timestamps is not None else [b.timestamp for b in self.builder.bars]
        previous = None
        for stamp in stamps:
            if previous is not None and stamp <= previous:
                raise InformationBoundaryError(
                    f"replay is not chronological: {stamp} follows {previous}"
                )
            parse_stamp(stamp)
            self.step(stamp)
            previous = stamp
        return self.journal

    def step(self, timestamp: str) -> dict:
        observation = self.builder.build(timestamp)
        prediction = self.predictor.predict(observation)
        costs = CostEstimate(
            estimated_usd=observation.estimated_cost_usd,
            version=COST_ASSUMPTION_VERSION,
        )
        decision = self.engine.decide(observation, prediction, self.uncertainty, costs)
        gate = self.gate.evaluate(
            observation, prediction, {"raw_decision": decision.raw_decision}
        )
        versions = versions_for(
            observation,
            model_id=prediction.model_id,
            decision_engine_version=self.engine.version,
            risk_gate_version=self.gate.version,
        )
        row = self.journal.record_decision(
            observation, prediction, self.uncertainty, costs, decision, gate, versions
        )
        self.processed.append(timestamp)
        return row
