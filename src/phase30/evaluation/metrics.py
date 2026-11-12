"""Cost-aware metric helpers wrapping Phase 14 scoring."""

from __future__ import annotations

from typing import Any

from phase14.scoring import cost_robustness, score_trades, session_vol_breakdown


def evaluate_trades(trades: list[dict], *, label: str, cost_mults: tuple[float, ...]) -> dict[str, Any]:
    score = score_trades(trades, label=label)
    cost = cost_robustness(trades, cost_mults)
    sess = session_vol_breakdown(trades)
    pooled = score["pooled"]
    # Average win/loss
    wins = [t["net_r"] for t in trades if t["net_r"] > 0]
    losses = [t["net_r"] for t in trades if t["net_r"] < 0]
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    return {
        "score": score,
        "cost_robustness": cost,
        "session_vol": sess,
        "avg_win_r": avg_win,
        "avg_loss_r": avg_loss,
        "n": pooled["n"],
        "mean_r": pooled["mean_r"],
        "median_r": pooled["median_r"],
        "net_r": pooled["net_r"],
        "profit_factor": pooled["profit_factor"],
        "win_rate": pooled["win_rate"],
        "max_drawdown_usd": pooled["max_drawdown_usd"],
        "bootstrap": pooled["bootstrap"],
    }
