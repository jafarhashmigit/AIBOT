"""Phase50 verdict selection — scientifically conservative."""

from __future__ import annotations

from typing import Any


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(payload["integrity_failure"])
    if payload.get("design_failure"):
        return "RESEARCH_DESIGN_FAILURE", str(payload["design_failure"])

    shadow_empty = bool(payload.get("agent_shadow_status") == "EMPTY")
    hist = payload.get("policy_summaries", {}).get("POLICY_1") or {}
    base = payload.get("policy_summaries", {}).get("POLICY_0") or {}
    controls = payload.get("controls") or {}

    incr = hist.get("incremental_value_vs_baseline")
    boot = hist.get("bootstrap_incremental") or {}
    changed = bool(hist.get("learning_changed_actions"))

    rand = (controls.get("randomized") or {}).get("incremental_value_vs_baseline")
    # Genuine learning needs: changes actions, positive incremental CI, beats randomized
    beats_random = (
        incr is not None
        and rand is not None
        and incr > rand + 1e-9
    )

    credible = bool(
        changed
        and incr is not None
        and incr > 0
        and boot.get("ok")
        and boot.get("bonferroni_excludes_zero")
        and boot.get("bonferroni_ci_low", -1) > 0
        and beats_random
    )

    promising = bool(
        changed
        and incr is not None
        and incr > 0
        and boot.get("ok")
        and boot.get("ci95_low", -1) > -0.05
        and not credible
    )

    if credible:
        msg = "Adaptive HISTORICAL experience produced chronologically stable incremental decision value over NO_LEARNING and beat randomized control."
        if shadow_empty:
            msg += " AGENT_SHADOW remains EMPTY — shadow learning not evaluated."
        return "LEARNING_VALUE_DEMONSTRATED", msg

    if promising:
        msg = "Directional improvement from HISTORICAL experience but evidence insufficient under corrected tests / controls."
        if shadow_empty:
            msg += " AGENT_SHADOW=EMPTY."
        return "LEARNING_VALUE_PROMISING_UNCONFIRMED", msg

    if shadow_empty and not changed:
        return (
            "NO_DEMONSTRATED_LEARNING_VALUE",
            "No demonstrated incremental decision value from HISTORICAL experience; AGENT_SHADOW=EMPTY so shadow learning unevaluable.",
        )

    # Also surface shadow empty as primary if that was the only intended test — mission allows both
    if shadow_empty and payload.get("prefer_shadow_status"):
        return "AGENT_SHADOW_EMPTY", "AGENT_SHADOW store empty; cannot evaluate shadow learning."

    return (
        "NO_DEMONSTRATED_LEARNING_VALUE",
        "Adaptive experience did not convincingly beat NO_LEARNING under chronological + control tests.",
    )
