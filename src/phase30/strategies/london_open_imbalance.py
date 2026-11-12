"""G: London UTC session directional imbalance (not NY SELL)."""

from __future__ import annotations

from typing import Any

from phase30.constants import STRATEGY_PARAMS
from phase30.indicators import directional_imbalance, utc_hour

P = STRATEGY_PARAMS["london_open_imbalance"]


def decide(ctx: dict[str, Any]) -> tuple[str, str, float]:
    t = ctx["decision_time"]
    hour = utc_hour(t)
    if hour < int(P["utc_hour_start"]) or hour >= int(P["utc_hour_end"]):
        return "WAIT", "outside_london_window", 0.0
    # Prefer London session flag when present, else hour gate alone.
    feat = ctx["feat"]
    if "corrected_session_london" in feat and float(feat["corrected_session_london"]) < 0.5:
        return "WAIT", "not_london_session_flag", 0.0
    imb = directional_imbalance(ctx["bars"], int(P["imb_bars"]))
    if imb is None:
        return "WAIT", "insufficient_history", 0.0
    thr = float(P["imb_min"])
    strength = abs(imb - 0.5) * 2.0
    if imb >= thr:
        return "BUY", "london_bull_imbalance", strength
    if imb <= (1.0 - thr):
        return "SELL", "london_bear_imbalance", strength
    return "WAIT", "london_balanced", strength
