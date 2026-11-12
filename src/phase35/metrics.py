"""Performance metrics — resolved vs unresolved kept separate."""

from __future__ import annotations

from typing import Any


def _max_dd(rs: list[float]) -> float:
    if not rs:
        return 0.0
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return float(dd)


def _longest_lose(rs: list[float]) -> int:
    best = cur = 0
    for r in rs:
        if r < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize_trades(trades: list[dict[str, Any]], *, decisions: dict[str, str] | None = None) -> dict[str, Any]:
    resolved = [t for t in trades if t.get("status") in {"PASS", "FAIL", "TIMEOUT"}]
    unresolved = [t for t in trades if t.get("status") == "UNRESOLVED_DATA_GAP"]
    rs = [float(t["net_r"]) for t in resolved]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    n_dec = len(decisions) if decisions else None
    n_buy = sum(1 for a in (decisions or {}).values() if a == "BUY") if decisions else sum(1 for t in trades if t.get("side") == "BUY")
    n_sell = sum(1 for a in (decisions or {}).values() if a == "SELL") if decisions else sum(1 for t in trades if t.get("side") == "SELL")
    n_wait = sum(1 for a in (decisions or {}).values() if a == "WAIT") if decisions else None
    mean_r = sum(rs) / len(rs) if rs else None
    return {
        "n_signals": n_buy + n_sell if decisions is None else sum(1 for a in decisions.values() if a in {"BUY", "SELL"}),
        "n_resolved": len(resolved),
        "n_unresolved": len(unresolved),
        "n_buy": n_buy,
        "n_sell": n_sell,
        "n_wait": n_wait,
        "n_decisions": n_dec,
        "win_pct": (len(wins) / len(rs) * 100.0) if rs else None,
        "mean_r": mean_r,
        "median_r": (sorted(rs)[len(rs) // 2] if rs else None),
        "net_r_sum": sum(rs) if rs else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else None),
        "avg_win": (sum(wins) / len(wins)) if wins else None,
        "avg_loss": (sum(losses) / len(losses)) if losses else None,
        "max_drawdown_r": _max_dd(rs),
        "longest_losing_streak": _longest_lose(rs),
        "expected_value_per_trade": mean_r,
        "gross_pnl": sum(float(t["net_pnl"]) for t in resolved) if resolved else 0.0,
        "est_execution_cost_sum": sum(float(t.get("costs") or 0) for t in resolved),
    }


def classify_result(summary: dict[str, Any], *, previous_mean_r: float | None) -> dict[str, Any]:
    from phase35.constants import MIN_RESOLVED_FOR_EVAL, MIN_RESOLVED_FOR_PROMISING

    n = int(summary.get("n_resolved") or 0)
    mean_r = summary.get("mean_r")
    if n < MIN_RESOLVED_FOR_EVAL or mean_r is None:
        verdict = "INSUFFICIENT_SAMPLE"
        edge = "cannot_be_evaluated"
    elif mean_r <= 0:
        verdict = "REJECTED"
        edge = "disappears" if (previous_mean_r is not None and previous_mean_r > 0) else "remains_nonpositive"
    elif n < MIN_RESOLVED_FOR_PROMISING:
        verdict = "UNCONFIRMED"
        edge = "survives_but_unconfirmed" if (previous_mean_r is None or previous_mean_r > 0) else "appears_positive_unconfirmed"
    else:
        verdict = "PROMISING"
        edge = "survives" if (previous_mean_r is not None and previous_mean_r > 0) else "positive_unconfirmed"
    if previous_mean_r is not None and mean_r is not None and n >= MIN_RESOLVED_FOR_EVAL:
        if previous_mean_r > 0 and mean_r <= 0:
            edge = "disappears"
        elif previous_mean_r > 0 and mean_r > 0 and mean_r < 0.5 * previous_mean_r:
            edge = "weakens_materially"
        elif previous_mean_r > 0 and mean_r < 0:
            edge = "reverses"
    return {"verdict": verdict, "edge_vs_previous": edge, "previous_mean_r": previous_mean_r}
