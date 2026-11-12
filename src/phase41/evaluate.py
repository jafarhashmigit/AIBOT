"""Primary evaluator — frozen H13_C and mean_reversion on Phase40 full-session data."""

from __future__ import annotations

from typing import Any, Callable

from phase41.constants import (
    COMMISSION_PER_SIDE_USD,
    HORIZON_BARS,
    SLIPPAGE_STRESS_USD,
    SPREAD_WIDEN_MULT,
    TARGET_DATES,
)
from phase41.data import load_day
from phase41.execution import apply_cost_scenario, simulate_trade
from phase41.features import build_feature_bundle
from phase41.metrics import (
    break_even_cost,
    by_date_all,
    by_session,
    day_block_bootstrap,
    leave_one_date_out,
    summarize,
)
from phase41.signals import decide_h13c_frozen, decide_mr_frozen


def _evaluate_candidate(candidate_id: str, decide_fn: Callable) -> dict[str, Any]:
    trades: list[dict[str, Any]] = []
    day_meta = []
    for day in TARGET_DATES:
        d = load_day(day)
        if d["m5_n"] == 0:
            day_meta.append({"day": day, "skipped": True, "reason": "NO_M5"})
            continue
        feat = build_feature_bundle(d["bars"], d["h1_bars"])
        times = feat["feature_times"]
        day_meta.append(
            {
                "day": day,
                "m5_n": d["m5_n"],
                "tick_n": d["tick_n"],
                "h1_bars": feat["h1_bars_available"],
                "h1_ema20_ready": feat["h1_ema20_ready"],
                "h1_warmup_before_day": d["h1_warmup_completed_before_day"],
            }
        )
        for i, t in enumerate(times):
            if i + HORIZON_BARS >= len(times):
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
    date_stats = by_date_all(trades, list(TARGET_DATES))
    session_stats = by_session(trades)
    boot = day_block_bootstrap(trades)
    lodo = leave_one_date_out(trades)
    be = break_even_cost(trades)

    scenarios = []
    for slip in SLIPPAGE_STRESS_USD:
        for comm in COMMISSION_PER_SIDE_USD:
            for widen in SPREAD_WIDEN_MULT:
                adj = [
                    apply_cost_scenario(
                        t, slippage_per_side=slip, commission_per_side=comm, spread_widen_mult=widen
                    )
                    for t in trades
                    if t.get("net_r") is not None and t.get("status") != "INSUFFICIENT_TICK_COVERAGE"
                ]
                if not adj:
                    continue
                mean_r = sum(float(x["scenario_net_r"]) for x in adj) / len(adj)
                pct_pos = sum(1 for x in adj if float(x["scenario_net_r"]) > 0) / len(adj)
                buy = [x for x in adj if x.get("side") == "BUY"]
                sell = [x for x in adj if x.get("side") == "SELL"]
                scenarios.append(
                    {
                        "slippage_per_side": slip,
                        "commission_per_side": comm,
                        "spread_widen_mult": widen,
                        "n": len(adj),
                        "mean_scenario_net_r": mean_r,
                        "pct_trades_positive": pct_pos,
                        "buy_mean_r": (sum(float(x["scenario_net_r"]) for x in buy) / len(buy)) if buy else None,
                        "sell_mean_r": (sum(float(x["scenario_net_r"]) for x in sell) / len(sell)) if sell else None,
                        "hypothetical": True,
                    }
                )

    n_dates_scored = sum(1 for d, v in date_stats.items() if (v.get("n") or 0) > 0)
    return {
        "candidate_id": candidate_id,
        "day_meta": day_meta,
        "summary": summary,
        "by_date": date_stats,
        "by_session": session_stats,
        "bootstrap": boot,
        "leave_one_date_out": lodo,
        "break_even": be,
        "scenarios": scenarios,
        "trades": trades,
        "n_independent_dates_with_scores": n_dates_scored,
    }


def evaluate_both() -> dict[str, Any]:
    h13 = _evaluate_candidate("H13_C", decide_h13c_frozen)
    mr = _evaluate_candidate("mean_reversion", decide_mr_frozen)
    return {"H13_C": h13, "mean_reversion": mr}
