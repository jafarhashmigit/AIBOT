"""Cost multiplier sensitivity for Phase30 strategies (diagnostic only)."""

from __future__ import annotations

import json
from typing import Any

from phase14.scoring import cost_robustness, stress_net_r
from phase30.base import generate_strategy_trades
from phase30.data import load_bundle
from phase30.strategies import STRATEGIES
from phase31.constants import COST_SENSITIVITY_MULTS, HOLDOUT_NAME, PHASE30_SUMMARY


def _breakeven_mult(trades: list[dict]) -> float | None:
    """Approximate multiplier where stressed mean_r crosses 0 (grid search)."""
    if not trades:
        return None
    # Fine grid diagnostic
    grid = [i / 100 for i in range(50, 201, 5)]
    last_pos = None
    for m in grid:
        xs = [stress_net_r(t["net_r"], t["initial_risk"], m) for t in trades]
        mean = sum(xs) / len(xs)
        if mean > 0:
            last_pos = m
        else:
            return last_pos
    return last_pos


def run_cost_sensitivity(*, strategies: tuple[str, ...] = ("vol_norm_momentum", "robust_mad_reversion", "body_persistence")) -> dict[str, Any]:
    if HOLDOUT_NAME in "xauusd_m5_test.csv" and False:
        pass
    bundle = load_bundle()
    assert bundle["bounds"]["holdout_opened"] is False

    # Also capture Phase30 stored 1x..2x where present
    stored = {}
    if PHASE30_SUMMARY.exists():
        summary = json.loads(PHASE30_SUMMARY.read_text(encoding="utf-8"))
        for sid, bl in summary["strategies"].items():
            stored[sid] = bl["metrics"].get("cost_robustness")

    out: dict[str, Any] = {"stored_phase30_cost_robustness": stored, "recomputed": {}, "diagnostic_only": True}
    for sid in strategies:
        if sid not in STRATEGIES:
            continue
        raw = generate_strategy_trades(bundle, STRATEGIES[sid], strategy_id=sid)
        trades = raw["trades"]
        # Pre-cost approximation: add costs/initial_risk back to net_r
        pre = []
        for t in trades:
            pre.append(t["net_r"] + (t["costs"] / t["initial_risk"] if t["initial_risk"] else 0.0))
        pre_mean = sum(pre) / len(pre) if pre else None
        sens = cost_robustness(trades, COST_SENSITIVITY_MULTS)
        # Map keys
        mapped = {f"{m:g}x": sens.get(f"{m:g}x") for m in COST_SENSITIVITY_MULTS}
        out["recomputed"][sid] = {
            "n": len(trades),
            "baseline_1x_mean_r": mapped.get("1x", {}).get("mean_r") if mapped.get("1x") else None,
            "approx_pre_cost_mean_r": pre_mean,
            "sensitivity": mapped,
            "approx_breakeven_cost_mult": _breakeven_mult(trades),
            "negative_even_before_approx_cost_addback": pre_mean is not None and pre_mean <= 0,
        }
    return out
