"""Immutable decision-time structures. Outcome fields cannot live here."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from phase6.constants import (
    FEATURE_VERSION_REF,
    OBSERVATION_VERSION,
    SYMBOL,
    TIMEFRAME,
)
from phase6.information_boundary import (
    InformationBoundaryError,
    assert_before_cutoff,
    assert_decision_time_payload,
    is_forbidden_key,
)


def _freeze_features(features: Mapping[str, float] | tuple[tuple[str, float], ...] | None):
    if features is None:
        return ()
    if isinstance(features, tuple):
        items = features
    else:
        items = tuple(sorted((str(k), float(v)) for k, v in features.items()))
    for name, _value in items:
        if is_forbidden_key(name):
            raise InformationBoundaryError(f"feature name is forbidden at decision time: {name}")
    return items


@dataclass(frozen=True, slots=True)
class MarketState:
    open: float
    high: float
    low: float
    close: float
    tick_volume: float
    spread: float | None = None


@dataclass(frozen=True, slots=True)
class Observation:
    """Decision-time observation. No realized outcome. No future prices."""

    timestamp: str
    market: str = SYMBOL
    timeframe: str = TIMEFRAME
    market_state: MarketState = field(default_factory=lambda: MarketState(0, 0, 0, 0, 0))
    features: tuple[tuple[str, float], ...] = ()
    feature_version: str = FEATURE_VERSION_REF
    observation_version: str = OBSERVATION_VERSION
    model_id: str = "no_model"
    estimated_cost_usd: float = 0.0
    available_history_end: str = ""
    data_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", _freeze_features(self.features))
        end = self.available_history_end or self.timestamp
        object.__setattr__(self, "available_history_end", end)
        if end != self.timestamp:
            raise InformationBoundaryError(
                "available_history_end must equal the observation timestamp "
                "(builder may only see history <= t)"
            )
        assert_before_cutoff(self.timestamp)
        assert_decision_time_payload(self.to_mapping())

    def feature_map(self) -> dict[str, float]:
        return {k: v for k, v in self.features}

    def to_mapping(self) -> dict[str, Any]:
        state = asdict(self.market_state)
        return {
            "timestamp": self.timestamp,
            "market": self.market,
            "timeframe": self.timeframe,
            "market_state": state,
            "features": dict(self.features),
            "feature_version": self.feature_version,
            "observation_version": self.observation_version,
            "model_id": self.model_id,
            "estimated_cost_usd": self.estimated_cost_usd,
            "available_history_end": self.available_history_end,
            "data_hash": self.data_hash,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Observation":
        assert_decision_time_payload(dict(payload))
        raw_state = payload.get("market_state") or {}
        state = MarketState(
            open=float(raw_state.get("open", 0.0)),
            high=float(raw_state.get("high", 0.0)),
            low=float(raw_state.get("low", 0.0)),
            close=float(raw_state.get("close", 0.0)),
            tick_volume=float(raw_state.get("tick_volume", 0.0)),
            spread=None if raw_state.get("spread") is None else float(raw_state["spread"]),
        )
        return cls(
            timestamp=str(payload["timestamp"]),
            market=str(payload.get("market", SYMBOL)),
            timeframe=str(payload.get("timeframe", TIMEFRAME)),
            market_state=state,
            features=payload.get("features") or {},
            feature_version=str(payload.get("feature_version", FEATURE_VERSION_REF)),
            observation_version=str(payload.get("observation_version", OBSERVATION_VERSION)),
            model_id=str(payload.get("model_id", "no_model")),
            estimated_cost_usd=float(payload.get("estimated_cost_usd", 0.0)),
            available_history_end=str(payload.get("available_history_end") or payload["timestamp"]),
            data_hash=str(payload.get("data_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class SideProba:
    tp: float
    sl: float
    time: float

    def __post_init__(self) -> None:
        total = self.tp + self.sl + self.time
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"side probabilities must sum to 1, got {total}")


@dataclass(frozen=True, slots=True)
class Prediction:
    """What the model believes. Not a trade decision."""

    buy: SideProba
    sell: SideProba
    expected_buy_r: float
    expected_sell_r: float
    model_id: str
    predictor_version: str


@dataclass(frozen=True, slots=True)
class Uncertainty:
    """Decision-time uncertainty. Estimated from training history, not future outcomes."""

    method: str
    buy: float
    sell: float


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Estimated round-trip cost at t. Not realized P&L."""

    estimated_usd: float
    version: str
    spread_floor_usd: float = 0.15
    extra_per_side_usd: float = 0.05


@dataclass(frozen=True, slots=True)
class SignalVersions:
    signal_id: str
    model_id: str
    feature_version: str
    decision_engine_version: str
    risk_gate_version: str
    cost_assumption_version: str
    observation_version: str
    journal_schema_version: str


ACTIONS = frozenset({"BUY", "SELL", "WAIT"})
