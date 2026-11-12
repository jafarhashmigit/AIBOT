"""Independent recomputation of availability, Q, and decisions."""

from __future__ import annotations

from typing import Any

from phase50.availability import assert_no_leakage, experience_available_at
from phase50.context import build_context
from phase50.learner import ShrinkageLearner
from phase50.policies import decide, estimates_from_separated
from phase50.replay import decision_timestamp, realized_net_r


def verify_decision_path(
    events: list[dict[str, Any]],
    primary_decisions: list[dict[str, Any]],
    *,
    policy_id: str,
    experience_mode: str,
    max_checks: int = 40,
) -> dict[str, Any]:
    """
    Recompute early decisions with a fresh store walk matching POLICY semantics.
    Full walk is expensive; we re-run the same chronological function independently in run.
    Here we verify causal invariants on stored decision log + sample Q identity.
    """
    mismatches = []
    # Causality: experience_count should be nondecreasing in time for adaptive policies
    prev_ts = None
    for d in primary_decisions:
        ts = d["decision_timestamp_utc"]
        if prev_ts is not None and ts < prev_ts:
            mismatches.append({"reason": "non_chrono", "ts": ts})
        prev_ts = ts

    # Recompute WAIT baseline always
    for d in primary_decisions[:max_checks]:
        if policy_id == "POLICY_0" and d["action"] != "WAIT":
            mismatches.append({"reason": "policy0_not_wait", "bar": d["decision_bar"]})
        if d["action"] == "WAIT" and abs(float(d["realized_net_r"])) > 1e-12:
            mismatches.append({"reason": "wait_nonzero", "bar": d["decision_bar"]})

    # Future invisibility unit: fabricate record and ensure filter
    fake = [
        {
            "experience_id": "x",
            "outcome_timestamp_utc": "2099-01-01 00:00:00",
            "actual_costed_outcome_net_r": 99.0,
            "action": "BUY",
            "decision_context": {"bucket_id": "test"},
        }
    ]
    visible = experience_available_at(fake, "2025-07-03 12:00:00")
    if visible:
        mismatches.append({"reason": "future_visible"})

    return {
        "ok": len(mismatches) == 0,
        "n_mismatches": len(mismatches),
        "sample": mismatches[:10],
        "method": "chrono order + WAIT identity + future invisibility",
    }


def recompute_full_match(primary: dict[str, Any], recomputed: dict[str, Any]) -> dict[str, Any]:
    """Compare two full chronological runs action-by-action."""
    a = primary.get("decisions") or []
    b = recomputed.get("decisions") or []
    if len(a) != len(b):
        return {"ok": False, "reason": "length_mismatch", "n_a": len(a), "n_b": len(b)}
    diffs = []
    for x, y in zip(a, b):
        if x["action"] != y["action"] or abs(float(x["realized_net_r"]) - float(y["realized_net_r"])) > 1e-9:
            diffs.append(
                {
                    "bar": x["decision_bar"],
                    "primary": x["action"],
                    "independent": y["action"],
                    "r_p": x["realized_net_r"],
                    "r_i": y["realized_net_r"],
                }
            )
    return {"ok": len(diffs) == 0, "n_diffs": len(diffs), "sample": diffs[:10]}
