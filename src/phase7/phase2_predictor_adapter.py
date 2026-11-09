"""Frozen Phase 2 OOS lookup implementing the Phase 6 Predictor interface."""

from __future__ import annotations

from typing import Any, Sequence

from phase6.predictor import Predictor
from phase6.schemas import Observation, Prediction, SideProba


class Phase2PredictorAdapter(Predictor):
    """Does not fit, retrain, recalibrate, or inspect outcomes."""

    def __init__(self, pairs: Sequence[dict]) -> None:
        self.table: dict[str, Prediction] = {}
        self.meta: dict[str, dict] = {}
        for pair in pairs:
            stamp = pair["timestamp"]
            buy, sell = pair["buy"], pair["sell"]
            self.table[stamp] = Prediction(
                buy=SideProba(buy["p_tp_rf"], buy["p_sl_rf"], buy["p_time_rf"]),
                sell=SideProba(sell["p_tp_rf"], sell["p_sl_rf"], sell["p_time_rf"]),
                expected_buy_r=float(buy["pred_r_rf"]),
                expected_sell_r=float(sell["pred_r_rf"]),
                model_id="phase2_rf_oos",
                predictor_version="phase2_oos_adapter_v1",
            )
            self.meta[stamp] = {
                "fold_id": pair["fold_id"],
                "training_period_end": pair["training_period_end"],
                "pred_r_ridge_BUY": buy.get("pred_r_ridge"),
                "pred_r_ridge_SELL": sell.get("pred_r_ridge"),
                "primary_clf_model_id_BUY": buy.get("primary_clf_model_id"),
                "primary_clf_model_id_SELL": sell.get("primary_clf_model_id"),
                "primary_reg_model_id_BUY": buy.get("primary_reg_model_id"),
                "primary_reg_model_id_SELL": sell.get("primary_reg_model_id"),
            }

    def fit(self, observations, outcomes, *, training_end: str) -> None:
        raise RuntimeError("Phase 7 Phase2PredictorAdapter cannot fit or retrain")

    def predict(self, observation: Observation) -> Prediction:
        if observation.timestamp not in self.table:
            raise KeyError(f"no frozen OOS prediction for {observation.timestamp}")
        return self.table[observation.timestamp]

    def predict_proba(self, observation: Observation) -> dict[str, dict[str, float]]:
        pred = self.predict(observation)
        return {
            "BUY": {"tp": pred.buy.tp, "sl": pred.buy.sl, "time": pred.buy.time},
            "SELL": {"tp": pred.sell.tp, "sl": pred.sell.sl, "time": pred.sell.time},
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "model_id": "phase2_rf_oos",
            "model_type": "frozen_phase2_oos_lookup",
            "fitted": False,
            "n": len(self.table),
            "status": "EXPERIMENTAL",
            "note": "Lookup only. Not a newly trained model.",
        }
