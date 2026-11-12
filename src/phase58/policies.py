"""Simple interpretable Phase58 decision rules — preregistered only."""

from __future__ import annotations

from typing import Any


def _stress(oc: dict[str, Any]) -> float | None:
    sn = (oc.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}
    v = sn.get("net_r")
    return float(v) if v is not None else None


def _pack(event: dict[str, Any], action: str) -> dict[str, Any]:
    if action == "WAIT":
        return {
            "day": event["day"],
            "decision_idx": event["decision_idx"],
            "action": "WAIT",
            "net_r": 0.0,
            "stress_net_r": 0.0,
            "hypothesis_id": event.get("hypothesis_id"),
        }
    oc = event["buy"] if action == "BUY" else event["sell"]
    return {
        "day": event["day"],
        "decision_idx": event["decision_idx"],
        "action": action,
        "net_r": float(oc["net_r"]) if oc.get("net_r") is not None else None,
        "stress_net_r": _stress(oc),
        "hypothesis_id": event.get("hypothesis_id"),
    }


def fit_thresholds(events: list[dict[str, Any]]) -> dict[str, float]:
    """Discovery-only fits for q75 spread_atr and q25 tick_volume."""
    sa = sorted(float(e["features"]["spread_atr"]) for e in events if e["features"].get("spread_atr") is not None)
    tv = sorted(float(e["features"]["tick_volume"]) for e in events if e["features"].get("tick_volume") is not None)
    def q(xs, p):
        if not xs:
            return None
        return xs[min(len(xs) - 1, int(p * (len(xs) - 1)))]
    return {
        "spread_atr_q75": q(sa, 0.75),
        "tick_volume_q25": q(tv, 0.25),
    }


def apply_H58_P1(event: dict[str, Any], _thr: dict[str, float] | None = None) -> dict[str, Any]:
    loc = event["features"].get("prior_session_location")
    if loc is None:
        return _pack(event, "WAIT")
    if loc <= 0.2:
        return _pack(event, "BUY")
    if loc >= 0.8:
        return _pack(event, "SELL")
    return _pack(event, "WAIT")


def apply_H58_W1(event: dict[str, Any], thr: dict[str, float]) -> dict[str, Any]:
    sa = event["features"].get("spread_atr")
    ret = event["features"].get("ret_1bar_mid")
    q = thr.get("spread_atr_q75")
    if sa is None or ret is None or q is None:
        return _pack(event, "WAIT")
    if sa > q:
        return _pack(event, "WAIT")
    return _pack(event, "BUY" if ret > 0 else "SELL")


def apply_H58_W1_nogate(event: dict[str, Any], thr: dict[str, float]) -> dict[str, Any]:
    """Control: same 1-bar sign rule without spread WAIT gate."""
    ret = event["features"].get("ret_1bar_mid")
    if ret is None:
        return _pack(event, "WAIT")
    return _pack(event, "BUY" if ret > 0 else "SELL")


def apply_H58_I1(event: dict[str, Any], thr: dict[str, float]) -> dict[str, Any]:
    tv = event["features"].get("tick_volume")
    ret = event["features"].get("ret_1bar_mid")
    q = thr.get("tick_volume_q25")
    if tv is None or ret is None or q is None:
        return _pack(event, "WAIT")
    if tv < q:
        return _pack(event, "WAIT")
    return _pack(event, "BUY" if ret > 0 else "SELL")


POLICIES = {
    "H58_P1_PRIOR_SESSION_LOCATION": apply_H58_P1,
    "H58_W1_COSTLY_SPREAD_WAIT": apply_H58_W1,
    "H58_I1_INACTIVITY_WAIT": apply_H58_I1,
}
