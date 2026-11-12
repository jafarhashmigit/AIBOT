"""Deterministic Phase65 policy functions."""

from __future__ import annotations

from typing import Any, Callable

from phase64_13.constants import OPEN


def fit_thresholds(discovery_events: list[dict[str, Any]]) -> dict[str, float]:
    atrs = [float(e["features"]["atr"]) for e in discovery_events if e["features"].get("atr")]
    comps = [
        float(e["features"]["range_compression"])
        for e in discovery_events
        if e["features"].get("range_compression") is not None
    ]
    abs_rets = [
        abs(float(e["features"]["ret_1bar_mid"]))
        for e in discovery_events
        if e["features"].get("ret_1bar_mid") is not None
    ]
    atrs_s = sorted(atrs)
    comps_s = sorted(comps)
    rets_s = sorted(abs_rets)

    def q(xs: list[float], p: float) -> float:
        if not xs:
            return 0.0
        i = min(len(xs) - 1, max(0, int(p * (len(xs) - 1))))
        return xs[i]

    return {
        "atr_q80": q(atrs_s, 0.80),
        "compression_q25": q(comps_s, 0.25),
        "abs_ret_median": q(rets_s, 0.50),
    }


def _decide(e: dict[str, Any], action: str) -> dict[str, Any]:
    if action == "WAIT":
        return {
            "day": e["day"],
            "decision_idx": e["decision_idx"],
            "action": "WAIT",
            "net_r": 0.0,
            "hypothesis_id": e.get("hypothesis_id"),
        }
    oc = e["buy"] if action == "BUY" else e["sell"]
    return {
        "day": e["day"],
        "decision_idx": e["decision_idx"],
        "action": action,
        "net_r": float(oc["net_r"]) if oc.get("net_r") is not None else None,
        "hypothesis_id": e.get("hypothesis_id"),
    }


def apply_H65_V1(e: dict[str, Any], thr: dict[str, float]) -> dict[str, Any]:
    f = e["features"]
    atr = f.get("atr")
    ret2 = f.get("ret_2bar_mid")
    if atr is None or atr >= thr["atr_q80"]:
        return _decide(e, "WAIT")
    if ret2 is None or ret2 == 0:
        return _decide(e, "WAIT")
    return _decide(e, "BUY" if ret2 > 0 else "SELL")


def apply_H65_C1(e: dict[str, Any], thr: dict[str, float]) -> dict[str, Any]:
    f = e["features"]
    comp = f.get("range_compression")
    ret1 = f.get("ret_1bar_mid")
    if comp is None or ret1 is None:
        return _decide(e, "WAIT")
    if comp <= thr["compression_q25"] and abs(ret1) >= thr["abs_ret_median"]:
        return _decide(e, "BUY" if ret1 > 0 else "SELL")
    return _decide(e, "WAIT")


def apply_H65_S1(e: dict[str, Any], thr: dict[str, float]) -> dict[str, Any]:
    f = e["features"]
    if f.get("session_state") != OPEN:
        return _decide(e, "WAIT")
    ret1 = f.get("ret_1bar_mid")
    if ret1 is None or ret1 == 0:
        return _decide(e, "WAIT")
    return _decide(e, "BUY" if ret1 > 0 else "SELL")


POLICIES: dict[str, Callable[[dict[str, Any], dict[str, float]], dict[str, Any]]] = {
    "H65_V1_ATR_REGIME_ABSTAIN": apply_H65_V1,
    "H65_C1_COMPRESSION_EXPANSION": apply_H65_C1,
    "H65_S1_SESSION_OPEN_FILTER": apply_H65_S1,
}
