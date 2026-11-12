"""Independent verification of EV arithmetic and policy decisions."""

from __future__ import annotations

from typing import Any

from phase47.ev import expected_net_r
from phase47.policy import decide, stress_ev_proxy


def verify_ev_rows(preds: list[dict[str, Any]], tol: float = 1e-9) -> dict[str, Any]:
    bad = []
    for i, p in enumerate(preds):
        if p.get("expected_net_r") is None:
            continue
        recomputed = expected_net_r(
            float(p["p_positive_net_r"]),
            float(p["expected_positive_net_r"]),
            float(p["expected_negative_net_r"]),
        )
        if abs(recomputed - float(p["expected_net_r"])) > tol:
            bad.append({"i": i, "primary": p["expected_net_r"], "independent": recomputed})
    return {"ok": len(bad) == 0, "n_checked": len(preds), "n_mismatches": len(bad), "sample": bad[:10]}


def verify_policy_decisions(decisions: list[dict[str, Any]], buy_preds: list[dict[str, Any]], sell_preds: list[dict[str, Any]]) -> dict[str, Any]:
    buy_map = {(p["day"], p["decision_bar"]): p for p in buy_preds}
    sell_map = {(p["day"], p["decision_bar"]): p for p in sell_preds}
    mismatches = []
    for d in decisions:
        k = (d["day"], d["decision_bar"])
        b = buy_map.get(k)
        s = sell_map.get(k)
        ind = decide(
            b,
            s,
            buy_stress_ev=stress_ev_proxy(b) if b else None,
            sell_stress_ev=stress_ev_proxy(s) if s else None,
        )
        if ind["decision"] != d["decision"]:
            mismatches.append({"key": k, "primary": d["decision"], "independent": ind["decision"]})
    return {
        "ok": len(mismatches) == 0,
        "n_checked": len(decisions),
        "n_mismatches": len(mismatches),
        "sample": mismatches[:10],
        "method": "re-run policy.decide without trusting stored decision field",
    }
