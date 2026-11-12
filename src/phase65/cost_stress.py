"""Execution-cost stress — never treat unknown commission/swap as zero."""

from __future__ import annotations

from typing import Any

from phase58.evaluation import calibrate
from phase65.evaluate import run_policy
from phase65.policies import fit_thresholds


def _stress_decision(d: dict[str, Any], *, spread_mult: float, slip_r: float, commission_r: float, swap_r: float) -> dict[str, Any]:
    """Apply labeled proxy stresses in R-units to non-WAIT decisions."""
    if d["action"] == "WAIT" or d.get("net_r") is None:
        return d
    # spread_mult approximates wider path friction; others are explicit UNKNOWN-bounded stresses
    adj = float(d["net_r"])
    # Re-scale as if spread friction increased (proxy): subtract (spread_mult-1)*0.05 R per trade
    adj -= (spread_mult - 1.0) * 0.05
    adj -= slip_r
    adj -= commission_r
    adj -= swap_r
    return {**d, "net_r": adj, "stressed": True}


def cost_taxonomy() -> dict[str, Any]:
    return {
        "spread": {"status": "PATH_BIDASK_INCLUDED", "account_specific": False, "in_experiment": True},
        "slippage": {"status": "UNKNOWN", "account_specific": True, "in_experiment": "STRESS_PROXY_ONLY"},
        "commission": {"status": "UNKNOWN", "account_specific": True, "in_experiment": "STRESS_PROXY_ONLY", "never_zero": True},
        "swap": {"status": "UNKNOWN_FOR_EXECUTION", "account_specific": True, "in_experiment": "STRESS_PROXY_ONLY", "never_zero": True},
        "conversion": {"status": "UNKNOWN", "in_experiment": False},
        "note": "Unknown costs are never converted to zero; stresses are labeled research proxies",
        "fully_execution_robust": False,
    }


def stress_hypothesis(
    hyp_id: str,
    events: list[dict[str, Any]],
    thr: dict[str, float] | None = None,
) -> dict[str, Any]:
    thr = thr or fit_thresholds(events)
    base = run_policy(events, hyp_id, thr)
    scenarios = {
        "spread_only_path": calibrate(base),
        "spread_stress_1_5x": calibrate([_stress_decision(d, spread_mult=1.5, slip_r=0, commission_r=0, swap_r=0) for d in base]),
        "slippage_stress_0_05R": calibrate([_stress_decision(d, spread_mult=1.0, slip_r=0.05, commission_r=0, swap_r=0) for d in base]),
        "commission_stress_0_05R": calibrate([_stress_decision(d, spread_mult=1.0, slip_r=0, commission_r=0.05, swap_r=0) for d in base]),
        "swap_stress_0_02R": calibrate([_stress_decision(d, spread_mult=1.0, slip_r=0, commission_r=0, swap_r=0.02) for d in base]),
        "combined_stress": calibrate(
            [_stress_decision(d, spread_mult=1.5, slip_r=0.05, commission_r=0.05, swap_r=0.02) for d in base]
        ),
    }
    mean0 = scenarios["spread_only_path"]["expected_net_r_all_decisions"] or 0.0
    # break-even: max additional R-cost per decision before EV<=0 (approx using trade rate)
    n = max(1, scenarios["spread_only_path"]["n_decisions"])
    n_tr = max(1, scenarios["spread_only_path"]["n_trades"])
    # If all-decision mean is m and trades fraction f, additional per-trade cost C kills EV when m - f*C <= 0
    f = n_tr / n
    breakeven = (mean0 / f) if f > 0 else None
    return {
        "hypothesis_id": hyp_id,
        "taxonomy": cost_taxonomy(),
        "scenarios": {k: {"expected_net_r_all_decisions": v.get("expected_net_r_all_decisions"), "n_trades": v.get("n_trades")} for k, v in scenarios.items()},
        "break_even_additional_R_per_trade": breakeven,
        "execution_robust_claim": False,
        "unknown_commission_treated_as_zero": False,
        "unknown_swap_treated_as_zero": False,
    }
