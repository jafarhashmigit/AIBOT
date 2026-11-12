"""Phase51 one-shot confirmation verdict."""

from __future__ import annotations

from typing import Any


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("integrity_failure"):
        return "DATA_INTEGRITY_FAILURE", str(payload["integrity_failure"])
    if payload.get("design_failure"):
        return "RESEARCH_DESIGN_FAILURE", str(payload["design_failure"])

    s = payload.get("frozen_summary") or {}
    wait = payload.get("wait_summary") or {}
    buy = payload.get("const_buy_summary") or {}
    sell = payload.get("const_sell_summary") or {}
    controls = payload.get("controls") or {}
    blocks = s.get("block_rows") or []

    mean_r = s.get("mean_net_r")
    incr = s.get("incremental_value_vs_baseline")
    boot = s.get("bootstrap_incremental") or {}
    rand = (controls.get("randomized") or {}).get("incremental_value_vs_baseline")

    pos_blocks = 0
    for b in blocks:
        if (b.get("mean_net_r") or 0) > 0:
            pos_blocks += 1
    majority_blocks = (pos_blocks / len(blocks) >= 0.5) if blocks else False

    beats_wait = incr is not None and incr > 0
    beats_const = (
        mean_r is not None
        and mean_r > (buy.get("mean_net_r") or -1e9)
        and mean_r > (sell.get("mean_net_r") or -1e9)
    )
    beats_random = incr is not None and rand is not None and incr > rand
    ci_ok = bool(boot.get("ok") and boot.get("ci95_low", -1) > 0)
    bonf_ok = bool(boot.get("ok") and boot.get("bonferroni_ci_low", -1) > 0)

    if (
        mean_r is not None
        and mean_r > 0
        and beats_wait
        and beats_const
        and majority_blocks
        and beats_random
        and ci_ok
        and bonf_ok
        and payload.get("leakage_ok")
        and payload.get("no_tuning")
    ):
        return (
            "EDGE_CANDIDATE_CONFIRMED",
            "Frozen Phase50 learner independently confirmed under preregistered acceptance standard.",
        )

    if mean_r is not None and mean_r > 0 and beats_wait and majority_blocks and beats_random:
        missing = []
        if not ci_ok:
            missing.append("CI95_includes_zero_or_missing")
        if not bonf_ok:
            missing.append("bonferroni_CI_includes_zero")
        if not beats_const:
            missing.append("does_not_beat_constant_baselines")
        return (
            "PROMISING_UNCONFIRMED",
            "Positive directional confirmation but statistically insufficient: " + ", ".join(missing),
        )

    return (
        "INDEPENDENT_CONFIRMATION_FAILED",
        "Frozen learner did not meet independent confirmation acceptance standard on sealed dates.",
    )
