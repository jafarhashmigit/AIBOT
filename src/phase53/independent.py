"""Independent recomputation checks on frozen policy decisions."""

from __future__ import annotations

from typing import Any

from phase53.policies import apply_policy
from phase49.stats import mean


def recompute_mean(events: list[dict[str, Any]], family_id: str, ood_bounds: dict[str, Any]) -> dict[str, Any]:
    decisions = apply_policy(events, family_id, ood_bounds=ood_bounds)
    nets = [float(d["net_r"]) for d in decisions if d.get("net_r") is not None]
    trades = [d for d in decisions if d["action"] in ("BUY", "SELL")]
    return {
        "family_id": family_id,
        "n_decisions": len(decisions),
        "n_trades": len(trades),
        "mean_net_r_all": mean(nets),
        "independent_recompute": True,
    }
