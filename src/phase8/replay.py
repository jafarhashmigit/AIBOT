"""Chronological experience replay. No preload. Frozen Phase 6 policy."""

from __future__ import annotations

from phase6.constants import COST_ASSUMPTION_VERSION
from phase6.decision_engine import DecisionEngine
from phase6.risk_gate import RiskGate, apply_gate
from phase6.schemas import CostEstimate, MarketState, Observation, Prediction, SideProba, Uncertainty
from phase6.versioning import observation_hash
from phase8.constants import RESEARCH_CUTOFF
from phase8.experience_builder import complete_experience, decision_time_from_phase7
from phase8.experience_schema import outcome_end_for
from phase8.experience_store import ExperienceStore

ESTIMATED_COST_USD = 0.25


def _prediction_from_row(row: dict, parsed: dict) -> Prediction:
    buy = parsed.get("buy") or {}
    sell = parsed.get("sell") or {}
    return Prediction(
        buy=SideProba(float(buy["tp"]), float(buy["sl"]), float(buy["time"])),
        sell=SideProba(float(sell["tp"]), float(sell["sl"]), float(sell["time"])),
        expected_buy_r=float(parsed.get("expected_buy_r", 0.0) or 0.0),
        expected_sell_r=float(parsed.get("expected_sell_r", 0.0) or 0.0),
        model_id=str(row.get("model_id") or "phase2_rf_oos"),
        predictor_version=str(parsed.get("predictor_version") or "phase2_oos_adapter_v1"),
    )


def _observation(timestamp: str) -> Observation:
    obs = Observation(
        timestamp=timestamp,
        market_state=MarketState(0.0, 0.0, 0.0, 0.0, 0.0, None),
        features=(),
        model_id="phase2_rf_oos",
        estimated_cost_usd=ESTIMATED_COST_USD,
        available_history_end=timestamp,
    )
    payload = obs.to_mapping()
    payload["data_hash"] = observation_hash(obs)
    return Observation.from_mapping(payload)


def frozen_decision(row: dict, parsed_pred: dict) -> tuple[str, str, str]:
    """Phase 6 engine + WAIT-only gate. Experience summary is not an input."""
    import json
    obs = _observation(row["timestamp"])
    pred = _prediction_from_row(row, parsed_pred)
    engine = DecisionEngine()
    gate = RiskGate()
    unc = Uncertainty(method="none", buy=0.0, sell=0.0)
    costs = CostEstimate(estimated_usd=ESTIMATED_COST_USD, version=COST_ASSUMPTION_VERSION)
    raw = engine.decide(obs, pred, unc, costs)
    gate_result = gate.evaluate(obs, pred, {"raw_decision": raw.raw_decision})
    final = apply_gate(raw.raw_decision, gate_result)
    reason = raw.reason if final == raw.raw_decision else f"gate_block:{gate_result.reason}"
    return raw.raw_decision, final, reason


def replay(decision_rows: list[dict], eval_by_ts: dict[str, dict], *, use_experience: bool) -> dict:
    store = ExperienceStore()
    pending: list[tuple[object, dict, str]] = []
    sizes = []
    leakage = []
    skipped = []
    records = []
    prev_size = 0
    engine = DecisionEngine()
    gate = RiskGate()
    import json

    stamps = [r["timestamp"] for r in decision_rows]
    for i in range(len(stamps) - 1):
        if stamps[i] > stamps[i + 1]:
            raise RuntimeError(f"non-chronological replay at {i}")

    for row in decision_rows:
        t = row["timestamp"]
        if t > RESEARCH_CUTOFF:
            raise RuntimeError("replay timestamp after cutoff")
        still = []
        for decision_fields, ev, end in pending:
            if end < t:
                rec, reason = complete_experience(decision_fields, ev)
                if rec is None:
                    skipped.append({"timestamp": decision_fields.timestamp, "reason": reason})
                else:
                    if rec.outcome_end >= t:
                        leakage.append({"timestamp": t, "bad_outcome_end": rec.outcome_end})
                    store.append(rec)
            else:
                still.append((decision_fields, ev, end))
        pending = still
        if len(store) < prev_size:
            leakage.append({"timestamp": t, "store_shrunk": True})
        prev_size = len(store)

        if use_experience:
            summary = store.summary(t)
            if summary.latest_outcome_end is not None and not (summary.latest_outcome_end < t):
                leakage.append({"timestamp": t, "future_visible": summary.latest_outcome_end})
        else:
            summary = store.summary("1970-01-01 00:00:00")

        parsed = json.loads(row["prediction"]) if isinstance(row.get("prediction"), str) else (row.get("prediction") or {})
        obs = _observation(t)
        pred = _prediction_from_row(row, parsed)
        unc = Uncertainty(method="none", buy=0.0, sell=0.0)
        costs = CostEstimate(estimated_usd=ESTIMATED_COST_USD, version=COST_ASSUMPTION_VERSION)
        raw = engine.decide(obs, pred, unc, costs)
        gate_result = gate.evaluate(obs, pred, {"raw_decision": raw.raw_decision})
        final = apply_gate(raw.raw_decision, gate_result)

        records.append({
            "timestamp": t,
            "fold_id": row.get("fold_id"),
            "raw_decision": raw.raw_decision,
            "final_decision": final,
            "experience_n": summary.n,
            "experience_latest_outcome_end": summary.latest_outcome_end,
            "experience_n_wait": summary.n_wait,
            "experience_n_buy": summary.n_buy,
            "experience_n_sell": summary.n_sell,
            "experience_mean_selected_r": summary.mean_selected_r,
            "use_experience": use_experience,
        })
        sizes.append(len(store))

        ev = eval_by_ts.get(t)
        if ev is None:
            skipped.append({"timestamp": t, "reason": "missing_evaluation_row"})
            continue
        decision_fields = decision_time_from_phase7(row)
        pending.append((decision_fields, ev, outcome_end_for(t)))

    # Remaining pending: horizon never reached inside this OOS window.
    for decision_fields, ev, end in pending:
        skipped.append({
            "timestamp": decision_fields.timestamp,
            "reason": "horizon_not_completed_before_next_oos_bar",
            "outcome_end": end,
        })

    n_buy = sum(1 for r in records if r["final_decision"] == "BUY")
    n_sell = sum(1 for r in records if r["final_decision"] == "SELL")
    n_wait = sum(1 for r in records if r["final_decision"] == "WAIT")
    by_fold = {}
    for fold in ("WF1", "WF2", "WF3"):
        part = [r for r in records if r.get("fold_id") == fold]
        ns = [r["experience_n"] for r in part]
        by_fold[fold] = {
            "decision_count": len(part),
            "final_BUY": sum(1 for r in part if r["final_decision"] == "BUY"),
            "final_SELL": sum(1 for r in part if r["final_decision"] == "SELL"),
            "final_WAIT": sum(1 for r in part if r["final_decision"] == "WAIT"),
            "experience_n_min": min(ns) if ns else 0,
            "experience_n_max": max(ns) if ns else 0,
            "experience_n_last": ns[-1] if ns else 0,
            "leakage_violations": 0,
        }
    leak_by_fold = {k: 0 for k in by_fold}
    for item in leakage:
        ts = item.get("timestamp")
        fold = next((r["fold_id"] for r in records if r["timestamp"] == ts), None)
        if fold in leak_by_fold:
            leak_by_fold[fold] += 1
    for fold, n in leak_by_fold.items():
        by_fold[fold]["leakage_violations"] = n

    return {
        "use_experience": use_experience,
        "n_decisions": len(records),
        "final_BUY": n_buy,
        "final_SELL": n_sell,
        "final_WAIT": n_wait,
        "store_size_end": len(store),
        "store_size_never_decreased": all(sizes[i] <= sizes[i + 1] for i in range(len(sizes) - 1)) if len(sizes) > 1 else True,
        "leakage_violations": leakage,
        "n_leakage": len(leakage),
        "skipped": skipped,
        "n_skipped": len(skipped),
        "records": records,
        "by_fold": by_fold,
        "experience_ids": store.snapshot_ids(),
    }
