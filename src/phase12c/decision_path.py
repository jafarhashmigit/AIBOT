"""Forward decision path. Fail-closed WAIT. Never bypasses RiskGate adapter."""

from __future__ import annotations

from phase12c.constants import CHAMPION, CHAMPION_STATUS, SOURCE_FORWARD
from phase12c.forward_observation import ForwardObservation, ForwardObservationError
from phase12c.gate_adapter import ForwardGateAdapter, ForwardGateAdapterError


class ForwardDecisionError(ValueError):
    pass


def _valid_prediction(prediction) -> bool:
    if prediction is None:
        return False
    if not isinstance(prediction, dict):
        return False
    required = ("expected_buy_r", "expected_sell_r", "model_id")
    return all(k in prediction for k in required)


def _valid_uncertainty(uncertainty) -> bool:
    if uncertainty is None:
        return False
    if not isinstance(uncertainty, dict):
        return False
    return "buy" in uncertainty and "sell" in uncertainty


def propose_raw_action(
    *,
    champion_id: str | None = None,
    prediction=None,
    uncertainty=None,
    model_id: str | None = None,
    required_features: list[str] | None = None,
    feature_map: dict | None = None,
) -> dict:
    """Fail-closed proposal. With NO_MODEL champion every path yields WAIT."""
    champ = champion_id if champion_id is not None else CHAMPION
    if champ != "no_model":
        return {
            "raw_action": "WAIT",
            "decision_reason": "UNKNOWN_OR_UNAPPROVED_MODEL",
            "model_status": "REJECTED",
            "accepted": False,
        }
    if model_id not in (None, "", "no_model"):
        return {
            "raw_action": "WAIT",
            "decision_reason": "UNKNOWN_MODEL_ID",
            "model_status": "REJECTED",
            "accepted": False,
        }
    if prediction is not None and not _valid_prediction(prediction):
        return {
            "raw_action": "WAIT",
            "decision_reason": "INVALID_PREDICTION",
            "model_status": "NO_MODEL",
            "accepted": False,
        }
    if prediction is None:
        return {
            "raw_action": "WAIT",
            "decision_reason": "NO_APPROVED_MODEL",
            "model_status": "NO_MODEL",
            "accepted": False,
        }
    # Even a structurally valid prediction cannot flip WAIT under no_model.
    if uncertainty is not None and not _valid_uncertainty(uncertainty):
        return {
            "raw_action": "WAIT",
            "decision_reason": "UNCERTAINTY_UNAVAILABLE",
            "model_status": "NO_MODEL",
            "accepted": False,
        }
    if uncertainty is None:
        return {
            "raw_action": "WAIT",
            "decision_reason": "UNCERTAINTY_UNAVAILABLE",
            "model_status": "NO_MODEL",
            "accepted": False,
        }
    if required_features:
        fmap = feature_map or {}
        missing = [f for f in required_features if f not in fmap]
        if missing:
            return {
                "raw_action": "WAIT",
                "decision_reason": "MISSING_REQUIRED_FEATURE",
                "model_status": "NO_MODEL",
                "accepted": False,
                "missing_features": missing,
            }
    return {
        "raw_action": "WAIT",
        "decision_reason": "NO_APPROVED_MODEL",
        "model_status": "NO_MODEL",
        "accepted": False,
    }


def decide_forward(
    observation: ForwardObservation,
    *,
    prediction=None,
    uncertainty=None,
    model_id: str | None = None,
    champion_id: str | None = None,
    required_features: list[str] | None = None,
    forced_raw_action: str | None = None,
) -> dict:
    """Produce a forward shadow decision. Always gated. Never invents BUY/SELL."""
    if not isinstance(observation, ForwardObservation):
        raise ForwardDecisionError("decide_forward requires ForwardObservation")
    if observation.data_quality_status not in {"ok", "warn"}:
        raise ForwardDecisionError("stale or invalid market data rejected")
    if not observation.complete:
        raise ForwardObservationError("incomplete candle rejected")

    proposal = propose_raw_action(
        champion_id=champion_id,
        prediction=prediction,
        uncertainty=uncertainty,
        model_id=model_id,
        required_features=required_features,
        feature_map=observation.features,
    )
    raw = forced_raw_action if forced_raw_action is not None else proposal["raw_action"]
    if raw not in {"BUY", "SELL", "WAIT"}:
        raw = "WAIT"
        proposal = {**proposal, "decision_reason": "INVALID_RAW_ACTION", "raw_action": "WAIT"}

    adapter = ForwardGateAdapter()
    try:
        gated = adapter.apply(raw)
    except ForwardGateAdapterError as exc:
        raise ForwardDecisionError(str(exc)) from exc

    final = gated["final_action"]
    if final != "WAIT" and CHAMPION_STATUS == "NO_MODEL":
        raise ForwardDecisionError("HARD FAILURE: NO_MODEL champion produced non-WAIT")

    return {
        "observation_id": observation.observation_id,
        "source_type": SOURCE_FORWARD,
        "timestamp": observation.timestamp,
        "is_post_cutoff": observation.to_mapping()["is_post_cutoff"],
        "model_id": model_id or "",
        "model_status": proposal["model_status"],
        "champion_status": CHAMPION_STATUS,
        "raw_action": raw,
        "decision_reason": proposal["decision_reason"],
        "risk_gate_result": gated["gate_status"],
        "final_action": final,
        "evaluate_called": False,
        "apply_gate_reused": True,
        "adapter_version": gated["adapter_version"],
        "full_evaluate_parity": gated["full_evaluate_parity"],
        "is_paper_trade": False,
        "is_paper_execution": False,
        "note": "Phase 12C forward path; RiskGate apply_gate reused; evaluate() not called",
    }
