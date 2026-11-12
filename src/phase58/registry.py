"""Preregistered Phase58 hypotheses — frozen before evaluation."""

from __future__ import annotations

from typing import Any

from phase58.constants import DO_NOT_REPEAT, canonical_json_sha256


HYPOTHESES: list[dict[str, Any]] = [
    {
        "id": "H58_P1_PRIOR_SESSION_LOCATION",
        "family": "prior_archived_session",
        "claim": (
            "Price location in the previous archived session range predicts costed H12 direction: "
            "bottom quintile → BUY, top quintile → SELL, else WAIT."
        ),
        "not_a_revival_of": ["H44_1", "H_A*", "C04_calendar_prior", "F1_CMC", "F2_EXF", "F3_SLF"],
        "action_rule": "prior_session_quintile_fade",
        "primary_metric": "expected_net_r_all_decisions",
        "min_trades": 20,
    },
    {
        "id": "H58_W1_COSTLY_SPREAD_WAIT",
        "family": "execution_cost_wait",
        "claim": (
            "When decision-bar spread/ATR exceeds discovery-fitted q75, WAIT; otherwise take the "
            "sign of the last completed M5 mid return (BUY if >0 else SELL). Improves mean net_R "
            "vs the same directional rule without the WAIT gate."
        ),
        "not_a_revival_of": ["H44_5", "H_E*", "F1_CMC"],
        "action_rule": "costly_spread_wait_then_1bar_sign",
        "primary_metric": "expected_net_r_all_decisions",
        "min_trades": 20,
    },
    {
        "id": "H58_I1_INACTIVITY_WAIT",
        "family": "inactivity",
        "claim": (
            "When tick_volume on the decision bar is below discovery-fitted q25, WAIT; otherwise "
            "follow 1-bar mid-return sign. Captures inactivity as WAIT opportunity, not a new "
            "momentum family."
        ),
        "not_a_revival_of": ["H42_G", "H_D*", "F3_SLF"],
        "action_rule": "inactivity_wait_then_1bar_sign",
        "primary_metric": "expected_net_r_all_decisions",
        "min_trades": 20,
    },
]


def build_registry() -> dict[str, Any]:
    overlap = [h["id"] for h in HYPOTHESES if h["id"] in DO_NOT_REPEAT]
    reg = {
        "preregistered": True,
        "n": len(HYPOTHESES),
        "hypotheses": HYPOTHESES,
        "do_not_repeat_enforced": True,
        "forbidden_id_collisions": overlap,
        "commission_slippage": "UNKNOWN_not_invented",
        "execution": "BUY ask→bid / SELL bid→ask / WAIT=0; horizon 12 M5; non-overlapping events",
    }
    assert not overlap, overlap
    reg["registry_sha256"] = canonical_json_sha256({k: v for k, v in reg.items() if k != "registry_sha256"})
    return reg
