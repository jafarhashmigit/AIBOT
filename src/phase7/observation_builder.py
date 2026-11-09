"""Build Phase 6 Observation from decision-time OOS information only."""

from __future__ import annotations

from phase6.information_boundary import InformationBoundaryError, assert_decision_time_payload
from phase6.schemas import MarketState, Observation
from phase6.versioning import observation_hash
from phase7.constants import ESTIMATED_COST_USD, FEATURE_VERSION


def build_observation(pair: dict) -> Observation:
    assert_decision_time_payload(pair, as_of=pair["timestamp"])
    if "buy" in pair:
        assert_decision_time_payload(pair["buy"], as_of=pair["timestamp"])
        assert_decision_time_payload(pair["sell"], as_of=pair["timestamp"])
    obs = Observation(
        timestamp=pair["timestamp"],
        market_state=MarketState(0.0, 0.0, 0.0, 0.0, 0.0, None),
        features=(),
        feature_version=pair.get("feature_version", FEATURE_VERSION),
        model_id="phase2_rf_oos",
        estimated_cost_usd=ESTIMATED_COST_USD,
        available_history_end=pair["timestamp"],
    )
    payload = obs.to_mapping()
    payload["data_hash"] = observation_hash(obs)
    built = Observation.from_mapping(payload)
    leaked = [k for k in built.to_mapping() if "actual" in k or "realized" in k]
    if leaked:
        raise InformationBoundaryError(f"observation leaked {leaked}")
    return built
