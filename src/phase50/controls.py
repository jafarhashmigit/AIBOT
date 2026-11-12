"""Negative and timing controls for learning-value claims."""

from __future__ import annotations

import random
from typing import Any, Callable

from phase50.replay import run_policy_chronological


def make_randomizer(seed: int = 50) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    def transform(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rng = random.Random(seed + len(batch))
        by_a: dict[str, list[float]] = {}
        for r in batch:
            by_a.setdefault(r["action"], []).append(float(r["actual_costed_outcome_net_r"]))
        for a in by_a:
            rng.shuffle(by_a[a])
        idx = {a: 0 for a in by_a}
        out = []
        for r in batch:
            a = r["action"]
            rec = dict(r)
            rec["actual_costed_outcome_net_r"] = by_a[a][idx[a]]
            idx[a] += 1
            rec["randomized"] = True
            out.append(rec)
        return out

    return transform


def run_controls(
    events: list[dict[str, Any]],
    *,
    day_to_block: dict[str, int],
    baseline_decisions_mean: float,
) -> dict[str, Any]:
    """
    E randomized experience (POLICY_1)
    F static experience (freeze after 60 experiences)
    G delayed learning (1 block delay)
    """
    from phase50.evaluation import summarize_run

    rand = run_policy_chronological(
        events,
        policy_id="POLICY_1",
        experience_mode="historical",
        outcome_transform=make_randomizer(50),
        day_to_block=day_to_block,
    )
    static = run_policy_chronological(
        events,
        policy_id="POLICY_1",
        experience_mode="historical",
        freeze_estimates_after_experiences=60,
        day_to_block=day_to_block,
    )
    delayed = run_policy_chronological(
        events,
        policy_id="POLICY_1",
        experience_mode="historical",
        delay_release_blocks=1,
        day_to_block=day_to_block,
    )

    return {
        "randomized": summarize_run(rand, baseline_mean=baseline_decisions_mean),
        "static": summarize_run(static, baseline_mean=baseline_decisions_mean),
        "delayed": summarize_run(delayed, baseline_mean=baseline_decisions_mean),
        "note": (
            "Real HISTORICAL learner must beat randomized control to support genuine learning. "
            "Adaptive should be compared to static for update value."
        ),
    }
