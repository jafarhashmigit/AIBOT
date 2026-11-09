"""Chronological Phase 6 agent on frozen Phase 2 OOS predictions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phase3.nplib import (
    GUARD,
    assert_holdout_untouched,
    holdout_status,
    install_guards,
    save,
    write_csv_dicts,
    wrap,
)
from phase6.constants import COST_ASSUMPTION_VERSION
from phase6.decision_engine import DecisionEngine
from phase6.journal import DecisionJournal, OUTCOME_FIELDS
from phase6.risk_gate import RiskGate, apply_gate
from phase6.schemas import CostEstimate, Uncertainty
from phase6.versioning import versions_for
from phase7.constants import (
    DECISIONS_PATH,
    ESTIMATED_COST_USD,
    EVALUATION_PATH,
    POLICY_ID,
    RECIPE_ID,
    REPORTS_DIR,
    RESEARCH_CUTOFF,
    SEED,
)
from phase7.evaluation import (
    POLICY_ORDER,
    baseline_actions,
    error_analysis,
    prediction_diagnostics,
    score_actions,
)
from phase7.observation_builder import build_observation
from phase7.oos_adapter import load_paired
from phase7.phase2_predictor_adapter import Phase2PredictorAdapter


def _assert_chronological(stamps: list[str]) -> dict:
    violations = []
    for i in range(len(stamps) - 1):
        if stamps[i] > stamps[i + 1]:
            violations.append({"i": i, "a": stamps[i], "b": stamps[i + 1]})
    if violations:
        raise RuntimeError(f"non-chronological timestamps: {violations[:5]}")
    return {"n": len(stamps), "violations": 0, "min": stamps[0] if stamps else None,
            "max": stamps[-1] if stamps else None}


def _csv_row(pair: dict, journal_row: dict, versions, raw: str, final: str, reason: str) -> dict:
    return {
        "decision_id": journal_row["decision_id"],
        "timestamp": pair["timestamp"],
        "side_context": "BUY+SELL",
        "model_id": versions.model_id,
        "feature_version": versions.feature_version,
        "decision_engine_version": versions.decision_engine_version,
        "risk_gate_version": versions.risk_gate_version,
        "prediction": json.dumps(journal_row["prediction"], separators=(",", ":")),
        "uncertainty": json.dumps(journal_row["uncertainty"], separators=(",", ":")),
        "estimated_cost": journal_row["estimated_cost"],
        "raw_decision": raw,
        "risk_gate_decision": journal_row["risk_gate_decision"],
        "final_decision": final,
        "decision_reason": reason,
        "fold_id": pair["fold_id"],
        "training_period_end": pair["training_period_end"],
        "signal_id": journal_row["signal_id"],
        "cost_assumption_version": versions.cost_assumption_version,
    }


def generate_agent_decisions(pairs: list[dict], predictor: Phase2PredictorAdapter):
    engine = DecisionEngine()
    gate = RiskGate()
    uncertainty = Uncertainty(method="none", buy=0.0, sell=0.0)
    costs = CostEstimate(estimated_usd=ESTIMATED_COST_USD, version=COST_ASSUMPTION_VERSION)
    journal = DecisionJournal()
    stamps = [p["timestamp"] for p in pairs]
    chrono = _assert_chronological(stamps)
    decision_rows = []
    raw_list = []
    final_list = []
    for pair in pairs:
        obs = build_observation(pair)
        pred = predictor.predict(obs)
        decision = engine.decide(obs, pred, uncertainty, costs)
        gate_result = gate.evaluate(obs, pred, {"raw_decision": decision.raw_decision})
        versions = versions_for(
            obs,
            model_id=pred.model_id,
            decision_engine_version=engine.version,
            risk_gate_version=gate.version,
        )
        journal_row = journal.record_decision(
            obs, pred, uncertainty, costs, decision, gate_result, versions
        )
        for name in OUTCOME_FIELDS:
            if name in journal_row:
                raise RuntimeError("decision-time journal contains an outcome field")
        final = apply_gate(decision.raw_decision, gate_result)
        decision_rows.append(_csv_row(pair, journal_row, versions, decision.raw_decision, final, journal_row["decision_reason"]))
        raw_list.append(decision.raw_decision)
        final_list.append(final)
    return decision_rows, raw_list, final_list, chrono, journal


def join_evaluation(decision_rows: list[dict], eval_pairs: list[dict]) -> list[dict]:
    by_ts = {e["timestamp"]: e for e in eval_pairs}
    out = []
    for row in decision_rows:
        ev = by_ts[row["timestamp"]]
        side = row["final_decision"]
        if side == "BUY":
            realized_r = ev["actual_net_r_BUY"]
            exit_reason = ev["actual_exit_reason_BUY"]
            realized_pnl = ev["actual_net_pnl_BUY"]
        elif side == "SELL":
            realized_r = ev["actual_net_r_SELL"]
            exit_reason = ev["actual_exit_reason_SELL"]
            realized_pnl = ev["actual_net_pnl_SELL"]
        else:
            realized_r = ""
            exit_reason = ""
            realized_pnl = ""
        out.append({
            "timestamp": row["timestamp"],
            "fold_id": row["fold_id"],
            "final_decision": row["final_decision"],
            "raw_decision": row["raw_decision"],
            "realized_outcome": exit_reason,
            "realized_R": realized_r,
            "exit_reason": exit_reason,
            "cost": row["estimated_cost"],
            "realized_pnl": realized_pnl,
            "actual_net_r_BUY": ev["actual_net_r_BUY"],
            "actual_net_r_SELL": ev["actual_net_r_SELL"],
            "actual_net_pnl_BUY": ev["actual_net_pnl_BUY"],
            "actual_net_pnl_SELL": ev["actual_net_pnl_SELL"],
            "actual_exit_reason_BUY": ev["actual_exit_reason_BUY"],
            "actual_exit_reason_SELL": ev["actual_exit_reason_SELL"],
            "evaluation_metadata": "joined_after_decisions",
        })
    return out


def main() -> int:
    install_guards()
    GUARD["cutoff"] = RESEARCH_CUTOFF
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    pairs, eval_pairs, integrity = load_paired()
    predictor = Phase2PredictorAdapter(pairs)
    decision_rows, raw_list, final_list, chrono, _journal = generate_agent_decisions(pairs, predictor)

    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_csv_dicts(DECISIONS_PATH, decision_rows)
    # Join only after the decision artifact exists on disk.
    if not DECISIONS_PATH.exists():
        raise RuntimeError("decision artifact missing before evaluation join")
    evaluation_rows = join_evaluation(decision_rows, eval_pairs)
    write_csv_dicts(EVALUATION_PATH, evaluation_rows)

    import numpy as np
    final = np.array(final_list, dtype=object)
    raw = np.array(raw_list, dtype=object)
    agent = score_actions(eval_pairs, final)
    baselines = baseline_actions(pairs, eval_pairs)
    baseline_scores = {name: score_actions(eval_pairs, actions) for name, actions in baselines.items()}
    payload = {
        "policy": POLICY_ID,
        "integrity": integrity,
        "chronology": chrono,
        "agent": agent,
        "agent_raw_distribution": {
            "BUY": int((raw == "BUY").sum()),
            "SELL": int((raw == "SELL").sum()),
            "WAIT": int((raw == "WAIT").sum()),
        },
        "baselines": baseline_scores,
        "diagnostics": prediction_diagnostics(pairs, eval_pairs),
        "error_analysis": error_analysis(eval_pairs, final, raw),
        "n_decisions": len(decision_rows),
        "max_timestamp": chrono["max"],
        "live_trading": False,
        "retrained": False,
        "ny_sell": False,
        "production": False,
        "policy_order": list(POLICY_ORDER),
    }
    save(REPORTS_DIR / "oos_agent_results.json",
         wrap("phase7_oos_agent", "exploratory", {"recipe": RECIPE_ID, "policy": POLICY_ID}, payload, SEED))
    assert_holdout_untouched()
    print("integrity", integrity["n"], integrity["unchanged"])
    print("chrono", chrono)
    print("final", agent["distribution"])
    print("raw", payload["agent_raw_distribution"])
    print("holdout", holdout_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
