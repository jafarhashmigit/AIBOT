"""Append-only decision journal. Outcomes are attached later, never at decision time."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from phase6.constants import JOURNAL_SCHEMA_VERSION, SYMBOL, TIMEFRAME
from phase6.decision_engine import DecisionResult
from phase6.information_boundary import InformationBoundaryError, is_forbidden_key
from phase6.outcome import Outcome, assert_horizon_complete
from phase6.risk_gate import GateResult, apply_gate
from phase6.schemas import CostEstimate, Observation, Prediction, SignalVersions, Uncertainty

DECISION_TIME_FIELDS = (
    "decision_id",
    "timestamp",
    "instrument",
    "timeframe",
    "observation_version",
    "feature_version",
    "model_version",
    "prediction",
    "uncertainty",
    "estimated_cost",
    "raw_decision",
    "risk_gate_decision",
    "final_decision",
    "decision_reason",
    "signal_id",
    "decision_engine_version",
    "risk_gate_version",
    "cost_assumption_version",
    "journal_schema_version",
    "observation_hash",
)

OUTCOME_FIELDS = (
    "realized_outcome",
    "realized_R",
    "exit_reason",
    "evaluation_timestamp",
)


def _prediction_snapshot(prediction: Prediction) -> dict:
    return {
        "buy": {"tp": prediction.buy.tp, "sl": prediction.buy.sl, "time": prediction.buy.time},
        "sell": {"tp": prediction.sell.tp, "sl": prediction.sell.sl, "time": prediction.sell.time},
        "expected_buy_r": prediction.expected_buy_r,
        "expected_sell_r": prediction.expected_sell_r,
        "model_id": prediction.model_id,
        "predictor_version": prediction.predictor_version,
    }


@dataclass
class DecisionJournal:
    rows: list[dict] = field(default_factory=list)
    schema_version: str = JOURNAL_SCHEMA_VERSION

    def record_decision(
        self,
        observation: Observation,
        prediction: Prediction,
        uncertainty: Uncertainty,
        costs: CostEstimate,
        decision: DecisionResult,
        gate: GateResult,
        versions: SignalVersions,
    ) -> dict:
        final = apply_gate(decision.raw_decision, gate)
        reason = decision.reason
        if final == "WAIT" and decision.raw_decision != "WAIT":
            reason = f"gate_block:{gate.reason}"
        row = {
            "decision_id": f"{observation.timestamp}_{observation.market}_{observation.timeframe}",
            "timestamp": observation.timestamp,
            "instrument": observation.market or SYMBOL,
            "timeframe": observation.timeframe or TIMEFRAME,
            "observation_version": versions.observation_version,
            "feature_version": versions.feature_version,
            "model_version": versions.model_id,
            "prediction": _prediction_snapshot(prediction),
            "uncertainty": {"method": uncertainty.method, "buy": uncertainty.buy, "sell": uncertainty.sell},
            "estimated_cost": costs.estimated_usd,
            "raw_decision": decision.raw_decision,
            "risk_gate_decision": gate.status,
            "final_decision": final,
            "decision_reason": reason,
            "signal_id": versions.signal_id,
            "decision_engine_version": versions.decision_engine_version,
            "risk_gate_version": versions.risk_gate_version,
            "cost_assumption_version": versions.cost_assumption_version,
            "journal_schema_version": self.schema_version,
            "observation_hash": observation.data_hash or versions.signal_id,
        }
        for key in row:
            if is_forbidden_key(key) or key in OUTCOME_FIELDS:
                raise InformationBoundaryError(f"decision record contains outcome field {key}")
        extra = set(row) - set(DECISION_TIME_FIELDS)
        if extra:
            raise InformationBoundaryError(f"unexpected decision-time fields: {sorted(extra)}")
        self.rows.append(row)
        return dict(row)

    def attach_outcome(
        self,
        decision_id: str,
        outcome: Outcome,
        *,
        evaluation_timestamp: str,
    ) -> dict:
        """Append an enrichment record. Does not mutate the original decision row."""
        original = None
        for row in self.rows:
            if row.get("decision_id") == decision_id and "realized_R" not in row:
                original = row
                break
        if original is None:
            raise KeyError(f"no decision-time row for {decision_id}")
        assert_horizon_complete(
            decision_timestamp=original["timestamp"],
            evaluation_timestamp=evaluation_timestamp,
        )
        enrichment = {
            "decision_id": decision_id,
            "kind": "outcome_enrichment",
            "realized_outcome": outcome.to_mapping(),
            "realized_R": outcome.net_return_r,
            "exit_reason": outcome.exit_reason,
            "evaluation_timestamp": evaluation_timestamp,
        }
        self.rows.append(enrichment)
        return dict(enrichment)

    def decision_time_rows(self) -> list[dict]:
        return [r for r in self.rows if r.get("kind") != "outcome_enrichment"]
