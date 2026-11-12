"""Frozen policy variants — evaluated separately."""

from __future__ import annotations

from typing import Any

from phase50.constants import EV_MARGIN_OVER_WAIT, LEARNER_VERSION, POLICY_VERSION
from phase50.learner import ShrinkageLearner


def policy_registry() -> dict[str, Any]:
    return {
        "POLICY_0_NO_LEARNING": {
            "id": "POLICY_0",
            "experience_mode": "none",
            "description": "No experience adaptation; always WAIT (insufficient evidence default)",
        },
        "POLICY_1_HISTORICAL_ONLY": {
            "id": "POLICY_1",
            "experience_mode": "historical",
            "description": "Learn only from HISTORICAL_HYPOTHETICAL",
        },
        "POLICY_2_SHADOW_ONLY": {
            "id": "POLICY_2",
            "experience_mode": "shadow",
            "description": "Learn only from AGENT_SHADOW",
        },
        "POLICY_3_DUAL": {
            "id": "POLICY_3",
            "experience_mode": "dual",
            "description": "Use both stores; contributions separately identifiable in diagnostics",
        },
        "policy_version": POLICY_VERSION,
        "learner_version": LEARNER_VERSION,
    }


def decide(
    *,
    policy_id: str,
    q: dict[str, Any] | None,
    experience_count: int,
) -> dict[str, Any]:
    """
    Select action from Q estimates.
    POLICY_0: always WAIT.
    Others: pick argmax among eligible actions with q_penalized > WAIT + margin and sufficient n.
    """
    if policy_id == "POLICY_0" or q is None:
        return {
            "action": "WAIT",
            "reason": "no_learning_baseline",
            "q": {"BUY": None, "SELL": None, "WAIT": 0.0},
            "policy_id": policy_id,
            "experience_count": experience_count,
        }

    candidates = []
    detail = {}
    for action in ("BUY", "SELL"):
        block = q.get(action) or {}
        qp = block.get("q_penalized")
        insuff = bool(block.get("insufficient_n", True))
        detail[action] = block
        if qp is None or insuff:
            continue
        if float(qp) > float(EV_MARGIN_OVER_WAIT):
            candidates.append((action, float(qp)))
    detail["WAIT"] = q.get("WAIT") or {"q": 0.0}

    if not candidates:
        return {
            "action": "WAIT",
            "reason": "no_eligible_action_vs_wait",
            "q": detail,
            "policy_id": policy_id,
            "experience_count": experience_count,
        }
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_a, best_q = candidates[0]
    return {
        "action": best_a,
        "reason": "max_penalized_q_over_wait",
        "selected_q": best_q,
        "q": detail,
        "policy_id": policy_id,
        "experience_count": experience_count,
    }


def estimates_from_separated(
    learner: ShrinkageLearner,
    bundles: dict[str, list[dict[str, Any]]],
    mode: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Build estimates with separately identifiable contributions.
    dual: combine lists for fitting but report n_hist / n_shadow separately.
    """
    if mode == "none":
        return {"n_experiences": 0, "global_mean": {}, "global_n": {}, "bucket_stats": {}}, {
            "n_historical": 0,
            "n_shadow": 0,
        }
    hist = bundles.get("HISTORICAL_HYPOTHETICAL") or []
    shadow = bundles.get("AGENT_SHADOW") or []
    if mode == "historical":
        used = hist
    elif mode == "shadow":
        used = shadow
    else:
        used = hist + shadow
    est = learner.fit_estimates(used)
    meta = {
        "n_historical": len(hist),
        "n_shadow": len(shadow),
        "n_used": len(used),
        "mode": mode,
    }
    return est, meta
