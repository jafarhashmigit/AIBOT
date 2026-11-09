"""Chronological Phase 9 replay. Expanding Ridge. Frozen RiskGate."""

from __future__ import annotations

from phase6.constants import COST_ASSUMPTION_VERSION
from phase6.schemas import CostEstimate, MarketState, Observation, Prediction, SideProba, Uncertainty
from phase6.versioning import observation_hash
from phase9.constants import RESEARCH_CUTOFF
from phase9.decision_policy import decide
from phase9.learner import ExperienceRidge, features_from_pair
from phase9.online_learning import OnlineLoop

ESTIMATED_COST_USD = 0.25


def _obs(timestamp: str) -> Observation:
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


def _rf_prediction(pair: dict) -> Prediction:
    buy, sell = pair["buy"], pair["sell"]
    return Prediction(
        buy=SideProba(float(buy["p_tp_rf"]), float(buy["p_sl_rf"]), float(buy["p_time_rf"])),
        sell=SideProba(float(sell["p_tp_rf"]), float(sell["p_sl_rf"]), float(sell["p_time_rf"])),
        expected_buy_r=float(buy["pred_r_rf"]),
        expected_sell_r=float(sell["pred_r_rf"]),
        model_id="phase2_rf_oos",
        predictor_version="phase2_oos_adapter_v1",
    )


def replay(
    pairs: list[dict],
    eval_rows: list[dict],
    *,
    use_learner: bool,
    ridge: ExperienceRidge | None = None,
) -> dict:
    stamps = [p["timestamp"] for p in pairs]
    for i in range(len(stamps) - 1):
        if stamps[i] > stamps[i + 1]:
            raise RuntimeError("HARD FAILURE: non-chronological replay")
    ev_by = {e["timestamp"]: e for e in eval_rows}
    loop = OnlineLoop(ridge if ridge is not None else ExperienceRidge()) if use_learner else None
    unc = Uncertainty(method="none", buy=0.0, sell=0.0)
    costs = CostEstimate(estimated_usd=ESTIMATED_COST_USD, version=COST_ASSUMPTION_VERSION)
    records = []
    fit_head: list[dict] = []
    fit_tail: list[dict] = []
    n_fits_logged = 0

    for pair in pairs:
        t = pair["timestamp"]
        if t > RESEARCH_CUTOFF:
            raise RuntimeError("HARD FAILURE: timestamp after cutoff")
        if loop is not None:
            loop.complete_due(t)
            latest = loop.ridge.buy.latest_outcome_end
            if latest is not None and not (latest < t):
                raise RuntimeError("HARD FAILURE: latest_experience_outcome_end >= T")
            n_avail = loop.ridge.buy.n
        else:
            latest = None
            n_avail = 0

        obs = _obs(t)
        mapping = obs.to_mapping()
        if any(k in mapping for k in ("realized_R", "actual_net_r", "exit_reason")):
            raise RuntimeError("HARD FAILURE: outcome in observation")
        rf_pred = _rf_prediction(pair)
        feat = features_from_pair(pair)

        if use_learner and loop is not None and loop.ridge.available():
            lb, ls = loop.ridge.predict(feat)
            loop.fits_available += 1
            source_expected = "experience_ridge"
            audit = loop.ridge.audit(fit_timestamp=t)
            n_fits_logged += 1
            if len(fit_head) < 2:
                fit_head.append(audit)
            fit_tail.append(audit)
            if len(fit_tail) > 5:
                fit_tail.pop(0)
        else:
            lb, ls = None, None
            source_expected = "cold_start_phase6_engine"
            if use_learner:
                loop.fallbacks += 1

        policy = decide(obs, rf_pred, unc, costs, lb, ls)
        if policy.source != source_expected:
            raise RuntimeError(
                f"HARD FAILURE: expected source {source_expected}, got {policy.source}"
            )
        records.append({
            "timestamp": t,
            "fold_id": pair["fold_id"],
            "raw_decision": policy.raw_decision,
            "final_decision": policy.final_decision,
            "reason": policy.reason,
            "source": policy.source,
            "pred_buy": policy.pred_buy,
            "pred_sell": policy.pred_sell,
            "n_experiences": n_avail,
            "latest_outcome_end": latest,
            "learner_train_n": n_avail,
            "max_training_outcome_end": latest,
            "gate_status": policy.gate_status,
        })
        ev = ev_by[t]
        if loop is not None:
            loop.enqueue(pair, ev)

    skipped = []
    if loop is not None:
        for item in loop.pending:
            skipped.append({
                "timestamp": item.pair["timestamp"],
                "reason": "horizon_not_completed_before_next_oos_bar",
                "outcome_end": item.outcome_end,
            })

    final = [r["final_decision"] for r in records]
    raw = [r["raw_decision"] for r in records]
    return {
        "use_learner": use_learner,
        "records": records,
        "n_decisions": len(records),
        "final_BUY": final.count("BUY"),
        "final_SELL": final.count("SELL"),
        "final_WAIT": final.count("WAIT"),
        "raw_BUY": raw.count("BUY"),
        "raw_SELL": raw.count("SELL"),
        "raw_WAIT": raw.count("WAIT"),
        "n_fallback": 0 if loop is None else loop.fallbacks,
        "n_learner_available": 0 if loop is None else loop.fits_available,
        "completed_experiences": 0 if loop is None else loop.completed,
        "skipped": skipped,
        "n_skipped": len(skipped),
        "n_leakage": 0,
        "max_timestamp": records[-1]["timestamp"] if records else None,
        "fit_audit_tail": fit_tail,
        "fit_audit_head": fit_head,
        "n_fits_logged": n_fits_logged,
    }
