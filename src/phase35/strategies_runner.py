"""Run frozen strategies on Phase 34 reconstructed features + bid/ask execution."""

from __future__ import annotations

from typing import Any, Callable

from phase25.strategies.breakout_retest import decide_breakout_retest
from phase25.strategies.mean_reversion import decide_mean_reversion
from phase25.strategies.mtf_h1_m5 import decide_mtf_h1_m5
from phase25.strategies.regime_router import decide_regime_router
from phase25.strategies.smc_liquidity import decide_smc_liquidity
from phase30.strategies import STRATEGIES as P30_STRATEGIES
from phase35.constants import H13C_FROZEN_CUTS, HORIZON_BARS
from phase35.execution import simulate_bidask_trade, simulate_legacy_trade, simulate_stress_trade
from phase35.features import build_h1_series, h1_trend_at
from phase35.metrics import classify_result, summarize_trades


def decide_h13c(feat: dict, h1_ctx: dict | None, cuts: dict) -> tuple[str, str]:
    """Verbatim frozen H13_C decision rule (Phase 14/16A). Local copy avoids numpy import chain."""
    if feat is None:
        return "WAIT", "missing_m5_features"
    if h1_ctx is None:
        return "WAIT", "missing_h1_context"
    c2e = float(feat["close_to_ema_20"])
    spread = float(feat["ema_9_20_spread"])
    if h1_ctx["h1_trend"] == "up":
        if c2e <= cuts["close_ema_low"] and spread > 0:
            return "BUY", "selected"
        return "WAIT", "h1_up_pullback_not_met"
    if h1_ctx["h1_trend"] == "down":
        if c2e >= cuts["close_ema_high"] and spread < 0:
            return "SELL", "selected"
        return "WAIT", "h1_down_pullback_not_met"
    return "WAIT", "unknown_h1_trend"

# Previous pooled mean_r from Phase 14/25/30 reports (comparison anchors).
PREVIOUS_MEAN_R = {
    "H13_C": 0.04856060840719428,
    "mean_reversion": -0.07520041102335161,
    "breakout_retest": -0.10010444891988272,
    "smc_liquidity": None,  # null in phase25 comparative
    "regime_router": -0.09090909090909442,
    "mtf_h1_m5": -0.020453238495809035,
    "vol_norm_momentum": -0.032667297112387264,
    "m15_trend_m5_trigger": -0.0494117107544147,
    "robust_mad_reversion": -0.04934843607006664,
    "body_persistence": None,
    "regime_cond_momentum": None,
    "regression_residual_mr": None,
    "wick_exhaustion": None,
    "compression_expansion": None,
    "momentum_structure_ensemble": None,
    "london_open_imbalance": None,
}


def _bars_for(feat_bundle: dict, decision_time: str, lookback: int = 120) -> list[dict] | None:
    idx = feat_bundle["feature_index"].get(decision_time)
    if idx is None:
        return None
    start = max(0, idx - lookback + 1)
    times = feat_bundle["feature_times"][start : idx + 1]
    bars = []
    for t in times:
        f = feat_bundle["features"].get(t)
        if f is None:
            continue
        # Strategy indicators expect open/high/low/close keys
        bars.append(f)
    return bars or None


def _ctx(feat_bundle: dict, decision_time: str, h1_series: list[dict], lookback: int = 120) -> dict | None:
    bars = _bars_for(feat_bundle, decision_time, lookback)
    feat = feat_bundle["features"].get(decision_time)
    if not bars or feat is None:
        return None
    # Require core features for strategies that need them
    if feat.get("atr_14") is None or feat.get("close_to_ema_20") is None:
        return None
    return {
        "decision_time": decision_time,
        "feat": feat,
        "bars": bars,
        "h1_ctx": h1_trend_at(h1_series, decision_time),
        "fold_id": "PHASE34_COVERAGE",
    }


def _decide_h13c(ctx: dict) -> tuple[str, str]:
    return decide_h13c(ctx["feat"], ctx["h1_ctx"], H13C_FROZEN_CUTS)


def strategy_registry() -> dict[str, dict[str, Any]]:
    """Frozen decide callables. Phase30 returns 3-tuple; Phase25/H13C return 2-tuple."""
    reg: dict[str, dict[str, Any]] = {
        "H13_C": {"decide": _decide_h13c, "arity": 2, "family": "benchmark"},
        "mean_reversion": {"decide": decide_mean_reversion, "arity": 2, "family": "phase25"},
        "breakout_retest": {"decide": decide_breakout_retest, "arity": 2, "family": "phase25"},
        "smc_liquidity": {"decide": decide_smc_liquidity, "arity": 2, "family": "phase25"},
        "regime_router": {"decide": decide_regime_router, "arity": 2, "family": "phase25"},
        "mtf_h1_m5": {"decide": decide_mtf_h1_m5, "arity": 2, "family": "phase25"},
    }
    for sid, decide in P30_STRATEGIES.items():
        reg[sid] = {"decide": decide, "arity": 3, "family": "phase30"}
    return reg


def evaluate_strategy(
    strategy_id: str,
    meta: dict[str, Any],
    *,
    feat_bundle: dict,
    times: list[str],
    by_time: dict,
    ticks_by_bar: dict,
) -> dict[str, Any]:
    decide = meta["decide"]
    arity = meta["arity"]
    h1_series = build_h1_series(feat_bundle["h1_rows"])
    decisions: dict[str, str] = {}
    exclusions: dict[str, str] = {}
    trades_ba: list[dict] = []
    trades_leg: list[dict] = []
    trades_stress: list[dict] = []

    # Warmup: need ATR + enough lookback; leave HORIZON_BARS+1 at end
    for i, t in enumerate(times):
        if i + 1 + HORIZON_BARS >= len(times):
            decisions[t] = "WAIT"
            exclusions[t] = "insufficient_forward_window"
            continue
        ctx = _ctx(feat_bundle, t, h1_series)
        if ctx is None:
            decisions[t] = "WAIT"
            exclusions[t] = "missing_context_or_warmup"
            continue
        try:
            if arity == 3:
                action, reason, _strength = decide(ctx)
            else:
                action, reason = decide(ctx)
        except Exception as exc:  # noqa: BLE001
            decisions[t] = "WAIT"
            exclusions[t] = f"decide_error:{type(exc).__name__}"
            continue
        if action not in {"BUY", "SELL", "WAIT"}:
            action, reason = "WAIT", "invalid_action"
        decisions[t] = action
        exclusions[t] = reason
        if action == "WAIT":
            continue

        atr = float(ctx["feat"]["atr_14"])
        if not atr or atr <= 0:
            decisions[t] = "WAIT"
            exclusions[t] = "invalid_atr"
            continue

        ba = simulate_bidask_trade(
            side=action,
            signal_idx=i,
            times=times,
            by_time=by_time,
            ticks_by_bar=ticks_by_bar,
            atr=atr,
        )
        leg = simulate_legacy_trade(side=action, signal_idx=i, times=times, by_time=by_time, atr=atr)
        stress = simulate_stress_trade(ba)
        base = {
            "decision_time": t,
            "side": action,
            "strategy_id": strategy_id,
            "day": t[:10],
        }
        trades_ba.append({**base, **ba})
        trades_leg.append({**base, **leg})
        trades_stress.append({**base, **stress})

    sum_ba = summarize_trades(trades_ba, decisions=decisions)
    sum_leg = summarize_trades(trades_leg, decisions=decisions)
    sum_stress = summarize_trades(trades_stress, decisions=decisions)
    prev = PREVIOUS_MEAN_R.get(strategy_id)

    # Chronological day groups among complete coverage days present in decisions
    days = sorted({t[:10] for t in times})
    groups = {
        "earliest": days[: max(1, len(days) // 3)],
        "middle": days[len(days) // 3 : 2 * len(days) // 3] or days,
        "latest": days[2 * len(days) // 3 :] or days,
    }
    chrono = {}
    for gname, gdays in groups.items():
        gset = set(gdays)
        gtrades = [t for t in trades_ba if t.get("day") in gset]
        chrono[gname] = {
            "days": gdays,
            "summary": summarize_trades(gtrades),
        }

    cls = classify_result(sum_ba, previous_mean_r=prev)
    # Downgrade PROMISING if chronological groups do not corroborate (6-day discipline).
    if cls["verdict"] == "PROMISING":
        pos_groups = 0
        for g in chrono.values():
            mr = g["summary"].get("mean_r")
            nr = int(g["summary"].get("n_resolved") or 0)
            if mr is not None and mr > 0 and nr >= 5:
                pos_groups += 1
        if pos_groups < 2:
            cls = {
                **cls,
                "verdict": "UNCONFIRMED",
                "edge_vs_previous": "positive_pooled_but_not_chrono_robust",
                "chrono_positive_groups": pos_groups,
            }

    return {
        "strategy_id": strategy_id,
        "family": meta["family"],
        "reproducible": True,
        "frozen_params_modified": False,
        "decisions_n": len(decisions),
        "view_a_historical_bidask": sum_ba,
        "view_b_legacy_frozen": sum_leg,
        "view_c_stress": sum_stress,
        "classification": cls,
        "chronological": chrono,
        "expectancy_delta_ba_minus_legacy": (
            None
            if sum_ba["mean_r"] is None or sum_leg["mean_r"] is None
            else sum_ba["mean_r"] - sum_leg["mean_r"]
        ),
        "trades_bidask": trades_ba,
        "n_pass": sum(1 for t in trades_ba if t.get("status") == "PASS"),
        "n_fail": sum(1 for t in trades_ba if t.get("status") == "FAIL"),
        "n_timeout": sum(1 for t in trades_ba if t.get("status") == "TIMEOUT"),
    }


def run_all_strategies(
    *,
    feat_bundle: dict,
    candle_pack: dict,
    ticks_by_bar: dict,
) -> dict[str, Any]:
    times = feat_bundle["feature_times"]
    by_time = candle_pack["by_time"]
    results = {}
    for sid, meta in strategy_registry().items():
        results[sid] = evaluate_strategy(
            sid,
            meta,
            feat_bundle=feat_bundle,
            times=times,
            by_time=by_time,
            ticks_by_bar=ticks_by_bar,
        )
        # Drop bulky trade lists from top-level export later — keep counts
    return results
