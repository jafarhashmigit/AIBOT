"""Independent recomputation path for Phase 36 replication."""

from __future__ import annotations

from typing import Any

from phase25.strategies.mean_reversion import decide_mean_reversion
from phase35.candles import build_m5_candles, ticks_by_m5
from phase35.execution import simulate_bidask_trade
from phase35.features import build_features, build_h1_series, h1_trend_at
from phase35.metrics import summarize_trades
from phase36.constants import HORIZON_BARS
from phase36.progress import write_json


def independent_recompute(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    """Second-path evaluation: rebuild candles/features and re-run decide + execution."""
    candle_pack = build_m5_candles(ticks)
    feat_bundle = build_features(candle_pack["candles"])
    times = feat_bundle["feature_times"]
    by_time = candle_pack["by_time"]
    tmap = ticks_by_m5(ticks)
    h1 = build_h1_series(feat_bundle["h1_rows"])
    trades = []
    n_buy = n_sell = 0
    for i, t in enumerate(times):
        if i + 1 + HORIZON_BARS >= len(times):
            continue
        idx = feat_bundle["feature_index"][t]
        start = max(0, idx - 119)
        bars = [feat_bundle["features"][x] for x in times[start : idx + 1]]
        feat = feat_bundle["features"][t]
        if feat.get("atr_14") is None:
            continue
        ctx = {"decision_time": t, "feat": feat, "bars": bars, "h1_ctx": h1_trend_at(h1, t)}
        action, _reason = decide_mean_reversion(ctx)
        if action not in {"BUY", "SELL"}:
            continue
        if action == "BUY":
            n_buy += 1
        else:
            n_sell += 1
        ba = simulate_bidask_trade(
            side=action,
            signal_idx=i,
            times=times,
            by_time=by_time,
            ticks_by_bar=tmap,
            atr=float(feat["atr_14"]),
        )
        trades.append({"decision_time": t, "side": action, "day": t[:10], **ba})
    summary = summarize_trades(trades)
    report = {
        "n_buy_signals": n_buy,
        "n_sell_signals": n_sell,
        "summary": summary,
        "n_trades": len(trades),
    }
    write_json("independent_recompute.json", report)
    return report


def compare_primary_vs_independent(primary: dict[str, Any], indep: dict[str, Any], *, tol: float = 1e-9) -> dict[str, Any]:
    a = primary.get("view_a_bidask") or {}
    b = indep.get("summary") or {}
    keys = ["n_resolved", "n_unresolved", "mean_r", "net_r_sum"]
    mismatches = []
    for k in keys:
        x, y = a.get(k), b.get(k)
        if x is None and y is None:
            continue
        if x is None or y is None or (isinstance(x, float) and abs(float(x) - float(y)) > tol) or (
            not isinstance(x, float) and x != y
        ):
            mismatches.append({"key": k, "primary": x, "independent": y})
    # signal counts
    if primary.get("n_buy_signals") != indep.get("n_buy_signals"):
        mismatches.append(
            {
                "key": "n_buy_signals",
                "primary": primary.get("n_buy_signals"),
                "independent": indep.get("n_buy_signals"),
            }
        )
    if primary.get("n_sell_signals") != indep.get("n_sell_signals"):
        mismatches.append(
            {
                "key": "n_sell_signals",
                "primary": primary.get("n_sell_signals"),
                "independent": indep.get("n_sell_signals"),
            }
        )
    out = {"ok": len(mismatches) == 0, "mismatches": mismatches, "tolerance": tol}
    write_json("independent_comparison.json", out)
    return out
