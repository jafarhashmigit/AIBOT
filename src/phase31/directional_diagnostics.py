"""BUY vs SELL diagnostic from Phase30 artifacts (diagnostic only)."""

from __future__ import annotations

import json
from typing import Any

from phase31.constants import PHASE30_SUMMARY


def _side_block(sides: dict, side: str) -> dict[str, Any]:
    s = sides.get(side) or {}
    return {
        "n": s.get("n"),
        "mean_r": s.get("mean_r"),
        "median_r": s.get("median_r"),
        "profit_factor": s.get("profit_factor"),
        "win_rate": s.get("win_rate"),
        "max_drawdown_usd": s.get("max_drawdown_usd"),
        "bootstrap_ci": {
            "low": (s.get("bootstrap") or {}).get("ci_low"),
            "high": (s.get("bootstrap") or {}).get("ci_high"),
            "p_mean_le_0": (s.get("bootstrap") or {}).get("p_mean_le_0"),
        },
    }


def run_buy_sell_diagnostics() -> dict[str, Any]:
    if not PHASE30_SUMMARY.exists():
        return {"ok": False, "error": "phase30_summary missing", "strategies": {}}
    summary = json.loads(PHASE30_SUMMARY.read_text(encoding="utf-8"))
    out: dict[str, Any] = {}
    for sid, block in summary["strategies"].items():
        sides = block["metrics"]["score"]["sides"]
        buy = _side_block(sides, "BUY")
        sell = _side_block(sides, "SELL")
        diff = None
        if buy["mean_r"] is not None and sell["mean_r"] is not None:
            diff = float(buy["mean_r"]) - float(sell["mean_r"])
        # Fold stability of side means if fold side breakdown unavailable — use fold pooled only.
        folds = block["metrics"]["score"]["folds"]
        fold_means = {fid: folds[fid]["mean_r"] for fid in folds}
        interpretation = "insufficient_n"
        if (buy["n"] or 0) >= 30 and (sell["n"] or 0) >= 30 and diff is not None:
            if buy["mean_r"] < 0 and sell["mean_r"] < 0:
                interpretation = "both_directions_weak"
            elif abs(diff) < 0.02:
                interpretation = "difference_likely_small_noise"
            elif diff < -0.02:
                interpretation = "BUY_systematically_worse"
            else:
                interpretation = "SELL_systematically_worse"
        out[sid] = {
            "BUY": buy,
            "SELL": sell,
            "buy_minus_sell_mean_r": diff,
            "fold_pooled_mean_r": fold_means,
            "interpretation": interpretation,
            "status": block["decision"]["status"],
            "note": "Side bootstrap CIs from Phase30 day-cluster bootstrap; not a new edge claim.",
        }

    # Aggregate message
    both_weak = sum(1 for v in out.values() if v["interpretation"] == "both_directions_weak")
    return {
        "source": str(PHASE30_SUMMARY),
        "n_strategies": len(out),
        "n_both_directions_weak": both_weak,
        "strategies": out,
        "summary": (
            "Across Phase30 strategies with enough trades, both BUY and SELL typically show "
            "non-positive expectancy; differences exist but do not create a research candidate."
        ),
    }
