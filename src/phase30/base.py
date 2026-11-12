"""Shared strategy runner — same execution contract as Phase 14/25."""

from __future__ import annotations

from typing import Any, Callable

from phase14.data import fold_of
from phase14.h1_trend import build_h1_series, h1_trend_at

DecisionFn = Callable[[dict[str, Any]], tuple[str, str, float]]


def build_context(
    *,
    bundle: dict,
    decision_time: str,
    h1_series: list[dict],
    lookback: int = 120,
) -> dict[str, Any] | None:
    idx = bundle["feature_index"].get(decision_time)
    if idx is None:
        return None
    start = max(0, idx - lookback + 1)
    times = bundle["feature_times"][start : idx + 1]
    bars = []
    for t in times:
        feat = bundle["features"].get(t)
        if feat is None:
            continue
        bars.append(feat)
    if not bars:
        return None
    feat = bundle["features"].get(decision_time)
    if feat is None:
        return None
    h1_ctx = h1_trend_at(h1_series, decision_time)
    return {
        "decision_time": decision_time,
        "feat": feat,
        "bars": bars,
        "h1_ctx": h1_ctx,
        "fold_id": fold_of(decision_time),
    }


def generate_strategy_trades(
    bundle: dict,
    decide: DecisionFn,
    *,
    strategy_id: str,
) -> dict[str, Any]:
    """Entry = next-bar open via precomputed eligible outcomes (same cost model)."""
    h1_series = build_h1_series(bundle["h1_rows"])
    decisions: dict[str, str] = {}
    strengths: dict[str, float] = {}
    exclusions: dict[str, str] = {}
    trade_rows: list[dict] = []

    for t in bundle["timestamps"]:
        fold_id = fold_of(t)
        if fold_id is None:
            decisions[t] = "WAIT"
            strengths[t] = 0.0
            exclusions[t] = "outside_wf_windows"
            continue
        ctx = build_context(bundle=bundle, decision_time=t, h1_series=h1_series)
        if ctx is None:
            decisions[t] = "WAIT"
            strengths[t] = 0.0
            exclusions[t] = "missing_context"
            continue
        action, reason, strength = decide(ctx)
        if action not in {"BUY", "SELL", "WAIT"}:
            action, reason, strength = "WAIT", "invalid_action", 0.0
        decisions[t] = action
        strengths[t] = float(strength)
        exclusions[t] = reason
        if action == "WAIT":
            continue
        outcome = bundle["outcomes"].get((t, action))
        if outcome is None:
            decisions[t] = "WAIT"
            exclusions[t] = "missing_eligible_outcome"
            continue
        feat = ctx["feat"]
        trade_rows.append(
            {
                "decision_time": t,
                "signal_time": t,
                "side": action,
                "fold_id": fold_id,
                "strategy_id": strategy_id,
                "signal_strength": float(strength),
                "net_r": outcome["net_r"],
                "net_pnl": outcome["net_pnl"],
                "initial_risk": outcome["initial_risk"],
                "costs": outcome["costs"],
                "entry_fill": outcome["entry_fill"],
                "exit_reason": outcome["exit_reason"],
                "entry_time": outcome["entry_time"],
                "exit_time": outcome["exit_time"],
                "h1_trend": (ctx["h1_ctx"] or {}).get("h1_trend"),
                "close_to_ema_20": float(feat["close_to_ema_20"]),
                "ema_9_20_spread": float(feat["ema_9_20_spread"]),
                "atr_14_pct": float(feat["atr_14_pct"]),
                "session_ny": int(float(feat.get("corrected_session_new_york", 0))),
                "session_london": int(float(feat.get("corrected_session_london", 0))),
            }
        )

    n_decisions = len(decisions)
    n_buy_sig = sum(1 for a in decisions.values() if a == "BUY")
    n_sell_sig = sum(1 for a in decisions.values() if a == "SELL")
    n_wait = sum(1 for a in decisions.values() if a == "WAIT")
    return {
        "strategy_id": strategy_id,
        "decisions": decisions,
        "strengths": strengths,
        "exclusions": exclusions,
        "trades": trade_rows,
        "n_decisions": n_decisions,
        "n_signals": n_buy_sig + n_sell_sig,
        "n_trades": len(trade_rows),
        "n_buy": sum(1 for r in trade_rows if r["side"] == "BUY"),
        "n_sell": sum(1 for r in trade_rows if r["side"] == "SELL"),
        "n_wait": n_wait,
        "signal_rate": (n_buy_sig + n_sell_sig) / n_decisions if n_decisions else 0.0,
        "signals_per_500": 500.0 * ((n_buy_sig + n_sell_sig) / n_decisions if n_decisions else 0.0),
    }
