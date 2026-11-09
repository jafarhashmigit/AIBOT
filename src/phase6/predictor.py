"""Model-agnostic predictor interface. Phase 6 does not train a production model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable, Mapping, Sequence

from phase6.constants import RESEARCH_CUTOFF
from phase6.information_boundary import InformationBoundaryError, assert_strictly_before
from phase6.schemas import Observation, Prediction, SideProba, Uncertainty


class Predictor(ABC):
    """Replaceable research predictor. Decision layer depends only on this contract."""

    @abstractmethod
    def fit(
        self,
        observations: Sequence[Observation],
        outcomes: Sequence[Any],
        *,
        training_end: str,
    ) -> None:
        """Train on history with outcome_known_at <= training_end. Not used for production in Phase 6."""

    @abstractmethod
    def predict(self, observation: Observation) -> Prediction:
        """Point prediction at decision time. Must not read outcomes."""

    @abstractmethod
    def predict_proba(self, observation: Observation) -> dict[str, dict[str, float]]:
        """Class probabilities per side: {BUY|SELL: {tp, sl, time}}."""

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        """Identity and training bounds. No evaluation-block metrics used as features."""


class NullPredictor(Predictor):
    """Honest Phase 6 stub: no trained edge. Uniform class probabilities, EV = 0."""

    def __init__(self, model_id: str = "no_model") -> None:
        self.model_id = model_id
        self.training_end: str | None = None
        self._fitted = False

    def fit(self, observations, outcomes, *, training_end: str) -> None:
        raise RuntimeError("Phase 6 does not train models")

    def predict(self, observation: Observation) -> Prediction:
        third = 1.0 / 3.0
        return Prediction(
            buy=SideProba(third, third, third),
            sell=SideProba(third, third, third),
            expected_buy_r=0.0,
            expected_sell_r=0.0,
            model_id=self.model_id,
            predictor_version="null_predictor_v1",
        )

    def predict_proba(self, observation: Observation) -> dict[str, dict[str, float]]:
        pred = self.predict(observation)
        return {
            "BUY": {"tp": pred.buy.tp, "sl": pred.buy.sl, "time": pred.buy.time},
            "SELL": {"tp": pred.sell.tp, "sl": pred.sell.sl, "time": pred.sell.time},
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": "null",
            "fitted": self._fitted,
            "training_end": self.training_end,
            "status": "EXPERIMENTAL",
            "note": "Architecture stub. Not a trading model.",
        }

    def uncertainty(self, observation: Observation) -> Uncertainty:
        return Uncertainty(method="none", buy=0.0, sell=0.0)


class ScriptedPredictor(Predictor):
    """Test double. Maps timestamps to predeclared predictions. Does not learn."""

    def __init__(self, table: Mapping[str, Prediction], *, training_end: str = "1970-01-01 00:00:00") -> None:
        self.table = dict(table)
        self.training_end = training_end
        self.model_id = "scripted_test"

    def fit(self, observations, outcomes, *, training_end: str) -> None:
        assert_strictly_before(training_end, RESEARCH_CUTOFF, what="training_end")
        for obs in observations:
            if obs.timestamp > training_end:
                raise InformationBoundaryError("fit received an observation after training_end")
        self.training_end = training_end

    def predict(self, observation: Observation) -> Prediction:
        if observation.timestamp <= self.training_end:
            raise InformationBoundaryError("predict on a timestamp inside the training window")
        if observation.timestamp not in self.table:
            raise KeyError(f"no scripted prediction for {observation.timestamp}")
        return self.table[observation.timestamp]

    def predict_proba(self, observation: Observation) -> dict[str, dict[str, float]]:
        pred = self.predict(observation)
        return {
            "BUY": {"tp": pred.buy.tp, "sl": pred.buy.sl, "time": pred.buy.time},
            "SELL": {"tp": pred.sell.tp, "sl": pred.sell.sl, "time": pred.sell.time},
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": "scripted_test",
            "training_end": self.training_end,
            "status": "EXPERIMENTAL",
            "n_scripted": len(self.table),
        }


def uniform_prediction(model_id: str = "no_model") -> Prediction:
    third = 1.0 / 3.0
    return Prediction(
        buy=SideProba(third, third, third),
        sell=SideProba(third, third, third),
        expected_buy_r=0.0,
        expected_sell_r=0.0,
        model_id=model_id,
        predictor_version="uniform_v1",
    )
