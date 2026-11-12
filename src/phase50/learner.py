"""Simple shrinkage action-value learner — interpretable, deterministic."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from phase50.constants import LEARNER_VERSION, MIN_EXPERIENCE_PER_ACTION, SHRINKAGE_K, UNCERTAINTY_PENALTY


class ShrinkageLearner:
    """
    Q(context, action) = shrink(bucket mean, global mean)
    WAIT always has Q=0 incremental (no opportunity cost).
    """

    def __init__(self, *, k: float = SHRINKAGE_K, min_n: int = MIN_EXPERIENCE_PER_ACTION):
        self.k = float(k)
        self.min_n = int(min_n)
        self.version = LEARNER_VERSION

    def fit_estimates(self, experiences: list[dict[str, Any]]) -> dict[str, Any]:
        """Build global and bucket stats from available experiences (already causal-filtered)."""
        global_by_action: dict[str, list[float]] = defaultdict(list)
        bucket_by_action: dict[tuple[str, str], list[float]] = defaultdict(list)

        for r in experiences:
            action = r["action"]
            if action == "WAIT":
                # WAIT outcomes are 0; still count for n but Q remains 0
                global_by_action["WAIT"].append(0.0)
                continue
            nr = float(r["actual_costed_outcome_net_r"])
            global_by_action[action].append(nr)
            bucket = (r.get("decision_context") or {}).get("bucket_id") or "unknown"
            bucket_by_action[(bucket, action)].append(nr)

        global_mean = {a: _mean(vs) for a, vs in global_by_action.items()}
        global_n = {a: len(vs) for a, vs in global_by_action.items()}
        global_std = {a: _std(vs) for a, vs in global_by_action.items()}

        bucket_stats = {}
        for (bucket, action), vs in bucket_by_action.items():
            bucket_stats[f"{bucket}|{action}"] = {
                "n": len(vs),
                "mean": _mean(vs),
                "std": _std(vs),
            }

        return {
            "learner_version": self.version,
            "global_mean": global_mean,
            "global_n": global_n,
            "global_std": global_std,
            "bucket_stats": bucket_stats,
            "n_experiences": len(experiences),
        }

    def q_values(
        self,
        estimates: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        bucket = context.get("bucket_id") or "unknown"
        out: dict[str, Any] = {"WAIT": {"q": 0.0, "n": estimates.get("global_n", {}).get("WAIT", 0), "source": "baseline_zero"}}
        for action in ("BUY", "SELL"):
            g_mean = float(estimates.get("global_mean", {}).get(action) or 0.0)
            g_n = int(estimates.get("global_n", {}).get(action) or 0)
            g_std = float(estimates.get("global_std", {}).get(action) or 1.0)
            key = f"{bucket}|{action}"
            b = (estimates.get("bucket_stats") or {}).get(key)
            if b and int(b["n"]) >= 1:
                n = int(b["n"])
                m = float(b["mean"])
                # shrinkage toward global
                q = (n / (n + self.k)) * m + (self.k / (n + self.k)) * g_mean
                std = float(b.get("std") or g_std)
                se = std / math.sqrt(max(n, 1))
            else:
                n = g_n
                q = g_mean
                se = g_std / math.sqrt(max(g_n, 1)) if g_n else 1.0
            # uncertainty penalty
            q_pen = q - UNCERTAINTY_PENALTY * se
            insufficient = n < self.min_n
            out[action] = {
                "q": q,
                "q_penalized": q_pen,
                "n": n,
                "se": se,
                "insufficient_n": insufficient,
                "bucket": bucket,
            }
        return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
