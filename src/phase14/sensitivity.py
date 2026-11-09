"""Predeclared limited sensitivity grid. Exploratory — does not select a new strategy."""

from __future__ import annotations

from phase14.constants import (
    PRIMARY_PULLBACK_Q_HIGH,
    PRIMARY_PULLBACK_Q_LOW,
    SENS_ENTRY_DELAY,
    SENS_H1_STRICT,
    SENS_PULLBACK_Q,
    SENS_SLIPPAGE_USD,
)
from phase14.scoring import cost_robustness, score_trades
from phase14.strategy import generate_h13c_trades


def run_sensitivity(bundle: dict) -> dict:
    rows = []
    primary_mean = None
    for q in SENS_PULLBACK_Q:
        for strict in SENS_H1_STRICT:
            for delay in SENS_ENTRY_DELAY:
                for slip in SENS_SLIPPAGE_USD:
                    q_high = 100 - q
                    gen = generate_h13c_trades(
                        bundle,
                        q_low=q,
                        q_high=q_high,
                        strict_gt=strict,
                        entry_delay_bars=delay,
                    )
                    scored = score_trades(gen["trades"], label=f"q{q}_strict{strict}_delay{delay}_slip{slip}")
                    stress = cost_robustness(gen["trades"], (1.0,), extra_slippage_usd=slip)
                    mean_r = scored["pooled"]["mean_r"]
                    is_primary = (
                        q == PRIMARY_PULLBACK_Q_LOW
                        and q_high == PRIMARY_PULLBACK_Q_HIGH
                        and strict is True
                        and delay == 0
                        and slip == 0.0
                    )
                    if is_primary:
                        primary_mean = mean_r
                    rows.append({
                        "q_low": q,
                        "q_high": q_high,
                        "strict_gt": strict,
                        "entry_delay_bars": delay,
                        "extra_slippage_usd": slip,
                        "n_trades": scored["pooled"]["n"],
                        "mean_r": mean_r,
                        "ci_low": scored["pooled"]["bootstrap"]["ci_low"],
                        "ci_high": scored["pooled"]["bootstrap"]["ci_high"],
                        "all_active_folds_positive": scored["all_active_folds_positive"],
                        "is_primary": is_primary,
                        "role": "confirmatory_primary" if is_primary else "exploratory_sensitivity",
                        "mean_r_at_1x_with_slip": stress["1x"]["mean_r"],
                    })

    signs = [r["mean_r"] > 0 for r in rows if r["mean_r"] == r["mean_r"] and r["n_trades"] >= 30]
    return {
        "grid_rows": rows,
        "n_grid_cells": len(rows),
        "primary_mean_r": primary_mean,
        "fraction_cells_positive_mean_r": (sum(1 for s in signs if s) / len(signs)) if signs else float("nan"),
        "note": (
            "Exploratory grid only. The best cell is NOT promoted. "
            "Primary rule remains q25/q75, strict H1 >, delay 0, slippage 0."
        ),
    }
