"""Evaluate frozen mean_reversion on independent Phase 36 corpus."""

from __future__ import annotations

from typing import Any

from phase25.strategies.mean_reversion import decide_mean_reversion
from phase35.candles import build_m5_candles, ticks_by_m5
from phase35.execution import simulate_bidask_trade, simulate_stress_trade
from phase35.features import build_features, build_h1_series, h1_trend_at
from phase35.metrics import summarize_trades
from phase36.constants import FROZEN_MEAN_REVERSION_PARAMS, HORIZON_BARS
from phase36.progress import write_json


def _ctx(feat_bundle: dict, decision_time: str, h1_series: list[dict], lookback: int = 120) -> dict | None:
    idx = feat_bundle["feature_index"].get(decision_time)
    if idx is None:
        return None
    start = max(0, idx - lookback + 1)
    times = feat_bundle["feature_times"][start : idx + 1]
    bars = [feat_bundle["features"][t] for t in times if t in feat_bundle["features"]]
    feat = feat_bundle["features"].get(decision_time)
    if not bars or feat is None:
        return None
    if feat.get("atr_14") is None or feat.get("atr_14_pct") is None:
        return None
    return {
        "decision_time": decision_time,
        "feat": feat,
        "bars": bars,
        "h1_ctx": h1_trend_at(h1_series, decision_time),
    }


def evaluate_mean_reversion(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    candle_pack = build_m5_candles(ticks)
    feat_bundle = build_features(candle_pack["candles"])
    times = feat_bundle["feature_times"]
    by_time = candle_pack["by_time"]
    tmap = ticks_by_m5(ticks)
    h1_series = build_h1_series(feat_bundle["h1_rows"])

    decisions: dict[str, str] = {}
    trades_ba: list[dict] = []
    trades_stress: list[dict] = []

    for i, t in enumerate(times):
        if i + 1 + HORIZON_BARS >= len(times):
            decisions[t] = "WAIT"
            continue
        ctx = _ctx(feat_bundle, t, h1_series)
        if ctx is None:
            decisions[t] = "WAIT"
            continue
        action, reason = decide_mean_reversion(ctx)
        decisions[t] = action
        if action not in {"BUY", "SELL"}:
            continue
        atr = float(ctx["feat"]["atr_14"])
        ba = simulate_bidask_trade(
            side=action,
            signal_idx=i,
            times=times,
            by_time=by_time,
            ticks_by_bar=tmap,
            atr=atr,
        )
        row = {"decision_time": t, "side": action, "day": t[:10], "reason": reason, **ba}
        trades_ba.append(row)
        trades_stress.append({"decision_time": t, "side": action, "day": t[:10], **simulate_stress_trade(ba)})

    summary = summarize_trades(trades_ba, decisions=decisions)
    stress = summarize_trades(trades_stress, decisions=decisions)

    # Per-day and chronological
    days = sorted({t[:10] for t in times})
    by_day = {}
    for d in days:
        dtrades = [x for x in trades_ba if x.get("day") == d]
        by_day[d] = summarize_trades(dtrades)

    groups = {
        "earliest": days[: max(1, len(days) // 3)],
        "middle": days[len(days) // 3 : 2 * len(days) // 3] or days,
        "latest": days[2 * len(days) // 3 :] or days,
    }
    chrono = {}
    for name, gdays in groups.items():
        gset = set(gdays)
        chrono[name] = {
            "days": gdays,
            "summary": summarize_trades([t for t in trades_ba if t.get("day") in gset]),
        }

    buy_tr = [t for t in trades_ba if t.get("side") == "BUY" and t.get("status") in {"PASS", "FAIL", "TIMEOUT"}]
    sell_tr = [t for t in trades_ba if t.get("side") == "SELL" and t.get("status") in {"PASS", "FAIL", "TIMEOUT"}]

    # Longest losing sequence already in summary
    report = {
        "strategy_id": "mean_reversion",
        "frozen_params": dict(FROZEN_MEAN_REVERSION_PARAMS),
        "n_m5_candles": candle_pack["n_candles"],
        "fabricated_candles": False,
        "view_a_bidask": summary,
        "view_c_stress_extra_005": stress,
        "by_day": by_day,
        "chronological": chrono,
        "buy_summary": summarize_trades(buy_tr),
        "sell_summary": summarize_trades(sell_tr),
        "n_buy_signals": sum(1 for a in decisions.values() if a == "BUY"),
        "n_sell_signals": sum(1 for a in decisions.values() if a == "SELL"),
        "n_wait": sum(1 for a in decisions.values() if a == "WAIT"),
        "trades": trades_ba,
        "params_modified": False,
    }
    write_json(
        "evaluation.json",
        {k: v for k, v in report.items() if k != "trades"}
        | {"trades_n": len(trades_ba), "trades_sample": trades_ba[:30]},
    )
    return report
