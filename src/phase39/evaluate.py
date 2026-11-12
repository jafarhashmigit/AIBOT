"""Evaluate frozen H13_C and mean_reversion separately on Phase38 data."""

from __future__ import annotations

from typing import Any

from phase39.constants import (
    COMMISSION_PER_SIDE_USD,
    SLIPPAGE_STRESS_USD,
    SPREAD_WIDEN_MULT,
)
from phase39.data import list_phase38_days, load_day
from phase39.execution import apply_cost_scenario, simulate_trade
from phase39.features import build_feature_bundle
from phase39.metrics import break_even_cost, by_date, day_block_bootstrap, summarize
from phase39.signals import decide_h13c_frozen, decide_mr_frozen


def _evaluate_candidate(candidate_id: str, decide_fn) -> dict[str, Any]:
    trades: list[dict[str, Any]] = []
    day_meta = []
    for day in list_phase38_days():
        d = load_day(day)
        if d["m5_n"] == 0:
            continue
        feat = build_feature_bundle(d["bars"])
        times = feat["feature_times"]
        day_meta.append(
            {
                "day": day,
                "m5_n": d["m5_n"],
                "tick_n": d["tick_n"],
                "h1_bars": feat["h1_bars_available"],
                "h1_ema20_ready": feat["h1_ema20_ready"],
            }
        )
        for i, t in enumerate(times):
            # Need room for entry + horizon in bar index space
            if i + 1 + 12 - 1 >= len(times):
                continue
            action, reason = decide_fn(feat, t)
            if action not in {"BUY", "SELL"}:
                continue
            atr = feat["features"][t].get("atr_14")
            if atr is None or float(atr) <= 0:
                trades.append(
                    {
                        "candidate": candidate_id,
                        "day": day,
                        "signal_time": t,
                        "side": action,
                        "signal_reason": reason,
                        "status": "INSUFFICIENT_TICK_COVERAGE",
                        "reason": "missing_atr",
                    }
                )
                continue
            sim = simulate_trade(
                side=action,
                signal_idx=i,
                times=times,
                ticks_by_bar=d["ticks_by_bar"],
                atr=float(atr),
                adverse_ambiguous=True,
            )
            # optimistic twin for uncertain
            opt = None
            if sim.get("uncertain"):
                opt = simulate_trade(
                    side=action,
                    signal_idx=i,
                    times=times,
                    ticks_by_bar=d["ticks_by_bar"],
                    atr=float(atr),
                    adverse_ambiguous=False,
                )
            trades.append(
                {
                    "candidate": candidate_id,
                    "day": day,
                    "signal_time": t,
                    "side": action,
                    "signal_reason": reason,
                    **sim,
                    "optimistic_net_r": (opt or {}).get("net_r"),
                }
            )

    summary = summarize(trades)
    date_stats = by_date(trades)
    boot = day_block_bootstrap(trades)
    be = break_even_cost(trades)

    # cost scenarios
    scenarios = []
    for slip in SLIPPAGE_STRESS_USD:
        for comm in COMMISSION_PER_SIDE_USD:
            for widen in SPREAD_WIDEN_MULT:
                adj = [apply_cost_scenario(t, slippage_per_side=slip, commission_per_side=comm, spread_widen_mult=widen) for t in trades if t.get("net_r") is not None and t.get("status") != "INSUFFICIENT_TICK_COVERAGE"]
                if not adj:
                    continue
                mean_r = sum(float(x["scenario_net_r"]) for x in adj) / len(adj)
                pct_pos = sum(1 for x in adj if float(x["scenario_net_r"]) > 0) / len(adj)
                scenarios.append(
                    {
                        "slippage_per_side": slip,
                        "commission_per_side": comm,
                        "spread_widen_mult": widen,
                        "n": len(adj),
                        "mean_scenario_net_r": mean_r,
                        "pct_trades_positive": pct_pos,
                    }
                )

    return {
        "candidate_id": candidate_id,
        "day_meta": day_meta,
        "summary": summary,
        "by_date": date_stats,
        "bootstrap": boot,
        "break_even": be,
        "scenarios": scenarios,
        "trades": trades,
        "n_independent_dates_with_scores": len(date_stats),
    }


def evaluate_both() -> dict[str, Any]:
    h13 = _evaluate_candidate("H13_C", decide_h13c_frozen)
    mr = _evaluate_candidate("mean_reversion", decide_mr_frozen)
    return {"H13_C": h13, "mean_reversion": mr}
