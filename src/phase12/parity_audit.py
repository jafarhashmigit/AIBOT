"""Phase 6 RiskGate vs Phase 12 frozen-gate parity. Does not modify Phase 6."""

from __future__ import annotations

from phase6.information_boundary import InformationBoundaryError
from phase6.risk_gate import RiskGate, apply_gate
from phase6.tests.factories import observation, prediction
from phase12.decision_recorder import apply_frozen_gate, propose_action
from phase12.validation import ShadowError

PRE_CUTOFF = "2026-06-19 10:00:00"
POST_CUTOFF = "2026-11-02 10:00:00"


def phase6_evaluate_final(raw_action: str, timestamp: str) -> tuple[str, str]:
    obs = observation(timestamp=timestamp)
    pred = prediction()
    result = RiskGate().evaluate(obs, pred, {"raw_decision": raw_action})
    return result.status, apply_gate(raw_action, result)


def pre_cutoff_table() -> dict:
    rows = []
    for raw in ("WAIT", "BUY", "SELL"):
        p6 = phase6_evaluate_final(raw, PRE_CUTOFF)
        p12 = apply_frozen_gate(raw)
        rows.append({
            "raw_action": raw,
            "phase6_evaluate": {"status": p6[0], "final_action": p6[1]},
            "phase12_frozen_gate": {"status": p12[0], "final_action": p12[1]},
            "match": p6 == p12,
            "final_is_wait": p6[1] == "WAIT" and p12[1] == "WAIT",
        })
    return {
        "timestamp": PRE_CUTOFF,
        "rows": rows,
        "all_match": all(r["match"] for r in rows),
        "all_final_wait": all(r["final_is_wait"] for r in rows),
    }


def post_cutoff_evaluate_attempt() -> dict:
    construction_error = None
    try:
        observation(timestamp=POST_CUTOFF)
        constructed = True
    except InformationBoundaryError as exc:
        constructed = False
        construction_error = str(exc)
    return {
        "timestamp": POST_CUTOFF,
        "observation_construction_raises": not constructed,
        "construction_error": construction_error,
        "evaluate_on_forward_observation": "NOT_REACHABLE",
        "exact_forward_evaluate_parity": "INCOMPLETE",
        "limitation": (
            "Phase 6 Observation.__post_init__ calls assert_before_cutoff. "
            "RiskGate.evaluate() also refuses post-cutoff timestamps. "
            "Phase 12 does not modify Phase 6, so evaluate() cannot run on forward bars. "
            "apply_frozen_gate() applies the same WAIT-only branches via GateResult + apply_gate. "
            "That is frozen-policy table application, not a claim that evaluate() supports "
            "forward observations."
        ),
    }


def unknown_model_cannot_bypass() -> dict:
    raised = False
    try:
        propose_action(champion_id="unknown_model_xyz")
    except ShadowError:
        raised = True
    return {"unknown_model_raises": raised, "cannot_bypass": raised}


def run_parity_audit() -> dict:
    pre = pre_cutoff_table()
    post = post_cutoff_evaluate_attempt()
    unknown = unknown_model_cannot_bypass()
    missing_model = propose_action()
    wait_only_table_pass = (
        pre["all_match"]
        and pre["all_final_wait"]
        and missing_model["raw_action"] == "WAIT"
        and unknown["cannot_bypass"]
        and post["observation_construction_raises"]
    )
    # Exact evaluate() parity on forward timestamps cannot be established.
    overall = "INCOMPLETE"
    return {
        "overall": overall,
        "wait_only_pre_cutoff_table": "PASS" if wait_only_table_pass else "FAIL",
        "forward_evaluate_parity": "INCOMPLETE",
        "pre_cutoff": pre,
        "post_cutoff": post,
        "unknown_model": unknown,
        "missing_model": {
            "model_status": missing_model["model_status"],
            "raw_action": missing_model["raw_action"],
            "decision_reason": missing_model["decision_reason"],
        },
        "phase6_evaluate_supports_forward_observations": False,
        "phase12_bypasses_gate": False,
        "notes": [
            "Pre-cutoff evaluate()+apply_gate matches apply_frozen_gate for WAIT/BUY/SELL.",
            "All compared finals are WAIT under frozen wait_only/no_model.",
            "Forward evaluate() parity is INCOMPLETE because Phase 6 refuses post-cutoff Observations.",
        ],
    }
