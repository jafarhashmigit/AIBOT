"""Portfolio-aware overlapping exposure accounting (hypothetical)."""

from __future__ import annotations

from typing import Any


def exposure_report(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Treat each OK directional trade as open from entry_timestamp to exit_timestamp.
    Unlimited-capital independent execution is NOT assumed as portfolio truth —
    this layer reports concurrency that would require stacked capital.
    """
    intervals: list[tuple[str, str, str, float]] = []
    for o in outcomes:
        if o.get("action") == "WAIT":
            continue
        if o.get("data_quality_status") != "OK":
            continue
        et = o.get("entry_timestamp")
        xt = o.get("exit_timestamp")
        if not et or not xt:
            continue
        risk = float(o.get("risk_amount") or 0.0)
        intervals.append((str(et), str(xt), str(o.get("action")), risk))

    if not intervals:
        return {
            "n_trades": 0,
            "max_concurrent_positions": 0,
            "max_concurrent_risk_sum": 0.0,
            "mean_concurrent_positions": 0.0,
            "note": "no_ok_directional_trades",
        }

    # Event sweep
    events: list[tuple[str, int, float]] = []
    for et, xt, _a, risk in intervals:
        events.append((et, +1, risk))
        events.append((xt, -1, risk))
    # Opens before closes at same timestamp
    events.sort(key=lambda e: (e[0], -e[1]))

    cur_n = 0
    cur_risk = 0.0
    max_n = 0
    max_risk = 0.0
    area_n = 0.0
    prev_t = None
    samples = 0
    for t, delta, risk in events:
        if prev_t is not None and t != prev_t:
            area_n += cur_n
            samples += 1
        cur_n += delta
        cur_risk += risk if delta > 0 else -risk
        max_n = max(max_n, cur_n)
        max_risk = max(max_risk, cur_risk)
        prev_t = t

    return {
        "n_trades": len(intervals),
        "max_concurrent_positions": max_n,
        "max_concurrent_risk_sum": max_risk,
        "mean_concurrent_positions": (area_n / samples) if samples else float(max_n),
        "unlimited_capital_assumption": False,
        "note": (
            "Overlapping hypothetical always-on policies stack exposure; "
            "portfolio EV ≠ sum of independent trade EVs under capital constraints."
        ),
    }
