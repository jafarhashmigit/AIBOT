"""Pre-cost vs post-cost decomposition for Phase30 strategies + H13_C."""

from __future__ import annotations

import json
from typing import Any

from phase14.scoring import score_trades
from phase14.strategy import generate_h13c_trades
from phase30.base import generate_strategy_trades
from phase30.data import load_bundle
from phase30.strategies import STRATEGIES
from phase32.constants import PHASE30_SUMMARY


STRATS = (
    "vol_norm_momentum",
    "m15_trend_m5_trigger",
    "robust_mad_reversion",
    "body_persistence",
)


def _block(trades: list[dict], *, use_gross: bool) -> dict[str, Any]:
    rows = []
    for t in trades:
        r = dict(t)
        if use_gross:
            # gross R ≈ net_r + costs/initial_risk
            add = (t["costs"] / t["initial_risk"]) if t["initial_risk"] else 0.0
            r["net_r"] = t["net_r"] + add
            r["net_pnl"] = t["net_pnl"] + t["costs"]
        rows.append(r)
    sc = score_trades(rows, label="gross" if use_gross else "net")
    p = sc["pooled"]
    return {
        "n": p["n"],
        "mean_r": p["mean_r"],
        "profit_factor": p["profit_factor"],
        "win_rate": p["win_rate"],
        "max_drawdown_usd": p["max_drawdown_usd"],
        "folds": {fid: {"n": sc["folds"][fid]["n"], "mean_r": sc["folds"][fid]["mean_r"]} for fid in sc["folds"]},
    }


def run_gross_net_analysis() -> dict[str, Any]:
    bundle = load_bundle()
    assert bundle["bounds"]["holdout_opened"] is False
    out: dict[str, Any] = {"strategies": {}, "diagnostic_only": True}

    # H13_C
    h = generate_h13c_trades(bundle)
    g = _block(h["trades"], use_gross=True)
    n = _block(h["trades"], use_gross=False)
    cost_r = None
    if g["mean_r"] is not None and n["mean_r"] is not None:
        cost_r = float(g["mean_r"] - n["mean_r"])
    out["strategies"]["H13_C"] = {
        "n": n["n"],
        "gross": g,
        "net": n,
        "total_cost_in_mean_r": cost_r,
        "class": _classify(g["mean_r"], n["mean_r"], n["n"]),
    }

    for sid in STRATS:
        raw = generate_strategy_trades(bundle, STRATEGIES[sid], strategy_id=sid)
        g = _block(raw["trades"], use_gross=True)
        n = _block(raw["trades"], use_gross=False)
        cost_r = None if g["mean_r"] is None or n["mean_r"] is None else float(g["mean_r"] - n["mean_r"])
        out["strategies"][sid] = {
            "n": n["n"],
            "gross": g,
            "net": n,
            "total_cost_in_mean_r": cost_r,
            "class": _classify(g["mean_r"], n["mean_r"], n["n"]),
        }

    # Cross-check vs Phase30 stored nets
    stored = {}
    if PHASE30_SUMMARY.exists():
        summary = json.loads(PHASE30_SUMMARY.read_text(encoding="utf-8"))
        for sid in STRATS:
            stored[sid] = summary["strategies"][sid]["metrics"]["score"]["pooled"]["mean_r"]
        stored["H13_C"] = summary["h13c_benchmark"]["metrics"]["score"]["pooled"]["mean_r"]
    out["phase30_stored_net_mean_r"] = stored
    return out


def _classify(gross_mean, net_mean, n: int) -> str:
    if n < 30:
        return "insufficient_sample"
    if gross_mean is None or net_mean is None:
        return "cannot_reconcile"
    if gross_mean <= 0:
        return "fails_even_before_costs"
    if gross_mean > 0 and net_mean <= 0:
        return "positive_gross_fails_after_costs"
    if net_mean > 0:
        return "positive_net_not_a_promotion"
    return "other"
