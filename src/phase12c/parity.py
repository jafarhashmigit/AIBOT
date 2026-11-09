"""Separate full evaluate parity from RiskGate apply_gate parity."""

from __future__ import annotations

from phase6.information_boundary import InformationBoundaryError
from phase6.risk_gate import RiskGate, apply_gate
from phase6.tests.factories import observation, prediction
from phase12c.constants import RESEARCH_CUTOFF_UTC
from phase12c.forward_observation import ForwardObservation
from phase12c.gate_adapter import ForwardGateAdapter

PRE_CUTOFF = "2026-06-19 10:00:00"
POST_CUTOFF = "2026-11-02 10:00:00"


def phase6_evaluate_apply(raw: str, timestamp: str) -> tuple[str, str]:
    obs = observation(timestamp=timestamp)
    pred = prediction()
    result = RiskGate().evaluate(obs, pred, {"raw_decision": raw})
    return result.status, apply_gate(raw, result)


def risk_gate_parity_audit() -> dict:
    adapter = ForwardGateAdapter()
    rows = []
    for raw in ("WAIT", "BUY", "SELL"):
        p6 = phase6_evaluate_apply(raw, PRE_CUTOFF)
        p12c = adapter.apply(raw)
        rows.append({
            "raw_action": raw,
            "phase6_evaluate_apply": {"status": p6[0], "final": p6[1]},
            "phase12c_adapter": {"status": p12c["gate_status"], "final": p12c["final_action"]},
            "match": p6 == (p12c["gate_status"], p12c["final_action"]),
            "final_is_wait": p6[1] == "WAIT" and p12c["final_action"] == "WAIT",
        })
    return {
        "concept": "B_RiskGate_and_apply_gate_parity",
        "timestamp": PRE_CUTOFF,
        "status": "PASS" if all(r["match"] and r["final_is_wait"] for r in rows) else "FAIL",
        "rows": rows,
        "evaluate_called_by_adapter": False,
        "apply_gate_reused": True,
    }


def full_evaluate_parity_audit() -> dict:
    construction_raises = False
    construction_error = None
    try:
        observation(timestamp=POST_CUTOFF)
    except InformationBoundaryError as exc:
        construction_raises = True
        construction_error = str(exc)

    evaluate_raises = False
    evaluate_error = None
    # evaluate cannot be reached without an Observation; document that.
    if construction_raises:
        evaluate_raises = True
        evaluate_error = "NOT_REACHABLE: Observation construction refused post-cutoff timestamp"

    return {
        "concept": "A_Full_Phase6_evaluate_parity",
        "status": "INCOMPLETE",
        "post_cutoff_timestamp": POST_CUTOFF,
        "research_cutoff": RESEARCH_CUTOFF_UTC,
        "observation_construction_raises": construction_raises,
        "construction_error": construction_error,
        "evaluate_on_forward_observation": "NOT_REACHABLE",
        "evaluate_error": evaluate_error,
        "claim": (
            "Full evaluate() parity is NOT PROVEN. Phase 6 Observation and "
            "RiskGate.evaluate refuse post-cutoff timestamps. Phase 12C does not "
            "modify Phase 6 and does not bypass those checks."
        ),
    }


def forward_compatibility_audit() -> dict:
    adapter = ForwardGateAdapter()
    obs = ForwardObservation(
        timestamp=POST_CUTOFF,
        bar_open_timestamp_utc="2026-11-02 09:55:00",
        bar_close_timestamp_utc=POST_CUTOFF,
        open=4000.0,
        high=4001.0,
        low=3999.0,
        close=4000.5,
        tick_volume=10,
    )
    from phase12c.decision_path import decide_forward

    decision = decide_forward(obs)
    buy_blocked = adapter.apply("BUY")["final_action"] == "WAIT"
    sell_blocked = adapter.apply("SELL")["final_action"] == "WAIT"
    wait_ok = adapter.apply("WAIT")["final_action"] == "WAIT"
    return {
        "concept": "C_Forward_observation_compatibility",
        "status": "PASS" if decision["final_action"] == "WAIT" and buy_blocked and sell_blocked and wait_ok else "FAIL",
        "forward_observation_accepted": True,
        "phase6_observation_used": False,
        "evaluate_called": decision["evaluate_called"],
        "apply_gate_reused": decision["apply_gate_reused"],
        "final_action": decision["final_action"],
        "adapter_version": decision["adapter_version"],
        "full_evaluate_parity": decision["full_evaluate_parity"],
        "qualification": (
            "Forward compatibility established for RiskGate apply_gate parity and "
            "fail-closed WAIT path. Full Phase 6 evaluate() parity remains NOT PROVEN."
        ),
    }


def run_compatibility_audits() -> dict:
    a = full_evaluate_parity_audit()
    b = risk_gate_parity_audit()
    c = forward_compatibility_audit()
    overall = "COMPLETE_WITH_QUALIFICATION"
    if b["status"] != "PASS" or c["status"] != "PASS":
        overall = "REJECTED"
    elif a["status"] != "INCOMPLETE":
        overall = "INCOMPLETE"
    return {
        "overall": overall,
        "A_full_evaluate_parity": a,
        "B_risk_gate_apply_parity": b,
        "C_forward_compatibility": c,
        "adapter_config": ForwardGateAdapter().frozen_config(),
    }
