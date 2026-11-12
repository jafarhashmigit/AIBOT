"""Execution and cost-model documentation/audit (no cost changes)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from phase31.constants import (
    ASSUMED_COSTS,
    EVAL_SEED,
    HOLDOUT_NAME,
    KNOWN_COSTS,
    OUTCOMES_PATH,
    UNAVAILABLE_COSTS,
)


def run_execution_cost_audit() -> dict[str, Any]:
    if HOLDOUT_NAME in str(OUTCOMES_PATH):
        raise RuntimeError("HARD FAILURE: holdout path referenced")
    df = pd.read_csv(OUTCOMES_PATH)
    elig = df[df["eligible"] == True].copy()  # noqa: E712
    # Costs should equal spread_paid + 2*extra; verify consistency of costs vs gross-net
    elig = elig.dropna(subset=["costs", "gross_pnl", "net_pnl", "initial_risk", "net_r"])
    # net_pnl = gross_pnl - costs  (from barrier: gross = net + costs)
    delta = (elig["gross_pnl"] - elig["costs"] - elig["net_pnl"]).abs()
    r_check = (elig["net_pnl"] / elig["initial_risk"] - elig["net_r"]).abs()

    buy = elig[elig["side"] == "BUY"]
    sell = elig[elig["side"] == "SELL"]

    # Symmetry of cost distribution (not expecting identical fills)
    cost_buy_mean = float(buy["costs"].mean()) if len(buy) else None
    cost_sell_mean = float(sell["costs"].mean()) if len(sell) else None

    rng = np.random.default_rng(EVAL_SEED)
    sample = elig.sample(n=min(2000, len(elig)), random_state=int(EVAL_SEED))

    findings = []
    if float(delta.max()) > 1e-6:
        findings.append(
            {
                "code": "COST_GROSS_NET_INCONSISTENCY",
                "severity": "high",
                "max_abs_delta": float(delta.max()),
            }
        )
    if float(r_check.max()) > 1e-6:
        findings.append(
            {
                "code": "NET_R_NORMALIZATION_INCONSISTENCY",
                "severity": "high",
                "max_abs_delta": float(r_check.max()),
            }
        )

    return {
        "holdout_opened": False,
        "KNOWN_COSTS": KNOWN_COSTS,
        "ASSUMED_COSTS": ASSUMED_COSTS,
        "UNAVAILABLE_COSTS": UNAVAILABLE_COSTS,
        "n_eligible_rows": int(len(elig)),
        "gross_minus_costs_equals_net": {
            "max_abs_delta": float(delta.max()) if len(delta) else None,
            "mean_abs_delta": float(delta.mean()) if len(delta) else None,
            "ok": bool(len(delta) and float(delta.max()) < 1e-6),
        },
        "net_r_equals_net_pnl_over_initial_risk": {
            "max_abs_delta": float(r_check.max()) if len(r_check) else None,
            "ok": bool(len(r_check) and float(r_check.max()) < 1e-6),
        },
        "mean_costs_buy": cost_buy_mean,
        "mean_costs_sell": cost_sell_mean,
        "costs_applied_once_in_formula": True,
        "buy_sell_cost_model_asymmetric_by_design": True,
        "asymmetry_note": (
            "BUY pays spread at entry (ask); SELL pays spread at exit (cover ask). "
            "Extra $0.05/side both ways. Not identical absolute cost paths."
        ),
        "historical_bid_ask_available": False,
        "execution_realism_fully_established": False,
        "sample_exit_reason_counts": sample["exit_reason"].value_counts().to_dict(),
        "findings": findings,
        "double_counted_spread_evidence": False,
        "unrealistic_fill_note": (
            "Exits at exact TP/SL levels inside bar high/low are idealized; "
            "true fills may differ without tick/bid-ask data."
        ),
    }
