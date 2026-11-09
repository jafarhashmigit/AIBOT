"""Independent H13_C reconstruction. Does not import phase13 signal functions."""

from __future__ import annotations

from phase14.constants import (
    FOLDS,
    PRIMARY_PULLBACK_Q_HIGH,
    PRIMARY_PULLBACK_Q_LOW,
)
from phase14.data import fold_of, train_cutoff_for_fold
from phase14.h1_trend import build_h1_series, h1_trend_at


def _percentile_sorted(values: list[float], q: float) -> float:
    """Independent percentile (linear interpolation), not np.percentile."""
    if not values:
        return float("nan")
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    pos = (q / 100.0) * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def train_pullback_cuts(
    bundle: dict,
    fold_id: str,
    *,
    q_low: float = PRIMARY_PULLBACK_Q_LOW,
    q_high: float = PRIMARY_PULLBACK_Q_HIGH,
) -> dict:
    cutoff = train_cutoff_for_fold(fold_id)
    vals = []
    for t in bundle["feature_times"]:
        if t > cutoff:
            break
        feat = bundle["features"].get(t)
        if feat is None:
            continue
        vals.append(float(feat["close_to_ema_20"]))
    return {
        "q_low": q_low,
        "q_high": q_high,
        "close_ema_low": _percentile_sorted(vals, q_low),
        "close_ema_high": _percentile_sorted(vals, q_high),
        "n_train": len(vals),
        "train_cutoff": cutoff,
    }


def decide_h13c(
    feat: dict,
    h1_ctx: dict | None,
    cuts: dict,
) -> tuple[str, str]:
    """Return (action, exclusion_reason)."""
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


def generate_h13c_trades(
    bundle: dict,
    *,
    q_low: float = PRIMARY_PULLBACK_Q_LOW,
    q_high: float = PRIMARY_PULLBACK_Q_HIGH,
    strict_gt: bool = True,
    entry_delay_bars: int = 0,
) -> dict:
    """Independent trade generation for H13_C variants."""
    h1_series = build_h1_series(bundle["h1_rows"])
    cuts_by_fold = {
        fid: train_pullback_cuts(bundle, fid, q_low=q_low, q_high=q_high) for fid in FOLDS
    }
    decisions: dict[str, str] = {}
    exclusions: dict[str, str] = {}
    trade_rows = []
    h1_hits = 0

    for t in bundle["timestamps"]:
        fold_id = fold_of(t)
        if fold_id is None:
            exclusions[t] = "outside_wf_windows"
            decisions[t] = "WAIT"
            continue
        # Optional confirmatory/exploratory delay: use features from prior completed bar
        signal_time = t
        if entry_delay_bars > 0:
            idx = bundle["feature_index"].get(t)
            if idx is None or idx < entry_delay_bars:
                decisions[t] = "WAIT"
                exclusions[t] = "entry_delay_unavailable"
                continue
            signal_time = bundle["feature_times"][idx - entry_delay_bars]

        feat = bundle["features"].get(signal_time)
        h1_ctx = h1_trend_at(h1_series, t, strict_gt=strict_gt)
        if h1_ctx is not None:
            h1_hits += 1
        action, reason = decide_h13c(feat, h1_ctx, cuts_by_fold[fold_id])
        decisions[t] = action
        exclusions[t] = reason
        if action == "WAIT":
            continue
        outcome = bundle["outcomes"].get((t, action))
        if outcome is None:
            exclusions[t] = "missing_eligible_outcome"
            decisions[t] = "WAIT"
            continue
        trade_rows.append({
            "decision_time": t,
            "signal_time": signal_time,
            "side": action,
            "fold_id": fold_id,
            "net_r": outcome["net_r"],
            "net_pnl": outcome["net_pnl"],
            "initial_risk": outcome["initial_risk"],
            "costs": outcome["costs"],
            "entry_fill": outcome["entry_fill"],
            "exit_reason": outcome["exit_reason"],
            "entry_time": outcome["entry_time"],
            "exit_time": outcome["exit_time"],
            "h1_trend": h1_ctx["h1_trend"] if h1_ctx else None,
            "close_to_ema_20": float(feat["close_to_ema_20"]) if feat else None,
            "ema_9_20_spread": float(feat["ema_9_20_spread"]) if feat else None,
            "atr_14_pct": float(feat["atr_14_pct"]) if feat else None,
            "session_ny": int(float(feat["corrected_session_new_york"])) if feat else None,
        })

    coverage = h1_hits / max(len(bundle["timestamps"]), 1)
    return {
        "decisions": decisions,
        "exclusions": exclusions,
        "trades": trade_rows,
        "cuts_by_fold": cuts_by_fold,
        "h1_coverage": coverage,
        "config": {
            "q_low": q_low,
            "q_high": q_high,
            "strict_gt": strict_gt,
            "entry_delay_bars": entry_delay_bars,
        },
        "n_selected_before_outcome": sum(1 for a in decisions.values() if a in {"BUY", "SELL"}),
        "n_trades": len(trade_rows),
    }
