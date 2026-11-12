"""I: Multi-bar body/range persistence (executable path structure)."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import body_range_ratio

P = STRATEGY_PARAMS["body_persistence"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    bars = ctx["bars"]
    n = int(P["persist_n"])
    if len(bars) < n:
        return "WAIT", "insufficient_history", 0.0
    seq = bars[-n:]
    thr = float(P["body_range_min"])
    bodies = [body_range_ratio(b) for b in seq]
    if any(br < thr for br in bodies):
        return "WAIT", "bodies_too_small", sum(bodies) / n
    ups = sum(1 for b in seq if float(b["close"]) > float(b["open"]))
    dns = sum(1 for b in seq if float(b["close"]) < float(b["open"]))
    strength = sum(bodies) / n
    if ups == n:
        return "BUY", "body_persist_up", strength
    if dns == n:
        return "SELL", "body_persist_down", strength
    return "WAIT", "no_body_persist", strength
