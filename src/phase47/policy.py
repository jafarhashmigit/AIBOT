"""Intelligent WAIT decision engine — thresholds frozen in constants."""

from __future__ import annotations

from typing import Any

from phase47.constants import POLICY_THRESHOLDS


def action_eligible(pred: dict[str, Any], *, stress_ev: float | None = None) -> tuple[bool, list[str]]:
    """Apply frozen rejection rules to a single action prediction."""
    th = POLICY_THRESHOLDS
    reasons: list[str] = []
    ev = pred.get("expected_net_r")
    unc = pred.get("prediction_uncertainty")
    fam = pred.get("market_familiarity")
    dq = pred.get("data_quality_status", "OK")

    if dq not in (None, "OK"):
        reasons.append("data_quality")
    if ev is None:
        reasons.append("missing_ev")
        return False, reasons
    if th["ev_strictly_positive"]:
        if not (float(ev) > float(th["ev_min_net_r"])):
            reasons.append("nonpositive_ev")
    elif float(ev) < float(th["ev_min_net_r"]):
        reasons.append("ev_below_min")

    if unc is None or float(unc) > float(th["max_prediction_uncertainty"]):
        reasons.append("high_uncertainty")
    if fam is None or float(fam) < float(th["min_market_familiarity"]):
        reasons.append("low_familiarity_ood")

    # Cost stress: use predicted EV haircut proxy = ev - (ev - stress_component)
    # Prefer provided stress_ev estimate; if None, require observed EV only (already checked)
    if stress_ev is not None:
        if not (float(stress_ev) > float(th["stress_ev_min_net_r"])):
            reasons.append("fails_cost_stress")

    return len(reasons) == 0, reasons


def decide(
    buy_pred: dict[str, Any] | None,
    sell_pred: dict[str, Any] | None,
    *,
    buy_stress_ev: float | None = None,
    sell_stress_ev: float | None = None,
) -> dict[str, Any]:
    """
    Deterministic policy:
      1-5 reject ineligible actions
      6 select eligible with highest EV
      7 else WAIT
    """
    candidates: list[tuple[str, dict[str, Any], float]] = []
    detail: dict[str, Any] = {"buy": None, "sell": None}

    if buy_pred is not None:
        ok, reasons = action_eligible(buy_pred, stress_ev=buy_stress_ev)
        detail["buy"] = {
            "eligible": ok,
            "reasons": reasons,
            "expected_net_r": buy_pred.get("expected_net_r"),
            "uncertainty": buy_pred.get("prediction_uncertainty"),
            "familiarity": buy_pred.get("market_familiarity"),
            "stress_ev": buy_stress_ev,
        }
        if ok:
            candidates.append(("BUY", buy_pred, float(buy_pred["expected_net_r"])))

    if sell_pred is not None:
        ok, reasons = action_eligible(sell_pred, stress_ev=sell_stress_ev)
        detail["sell"] = {
            "eligible": ok,
            "reasons": reasons,
            "expected_net_r": sell_pred.get("expected_net_r"),
            "uncertainty": sell_pred.get("prediction_uncertainty"),
            "familiarity": sell_pred.get("market_familiarity"),
            "stress_ev": sell_stress_ev,
        }
        if ok:
            candidates.append(("SELL", sell_pred, float(sell_pred["expected_net_r"])))

    if not candidates:
        return {
            "decision": "WAIT",
            "reason": "no_eligible_action",
            "detail": detail,
            "thresholds": POLICY_THRESHOLDS,
        }

    candidates.sort(key=lambda x: x[2], reverse=True)
    best_action, best_pred, best_ev = candidates[0]
    return {
        "decision": best_action,
        "reason": "max_eligible_ev",
        "selected_ev": best_ev,
        "detail": detail,
        "thresholds": POLICY_THRESHOLDS,
    }


def stress_ev_proxy(pred: dict[str, Any], haircut: float = 0.05) -> float | None:
    """
    Hypothetical stress on predicted EV (not live costs).
    Haircut labeled RESEARCH_PROXY — frozen small reduction for stress gate.
    """
    ev = pred.get("expected_net_r")
    if ev is None:
        return None
    return float(ev) - abs(float(haircut))


def apply_policy_to_paired(
    buy_preds: list[dict[str, Any]],
    sell_preds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pair BUY/SELL by (day, decision_bar) and decide."""
    buy_map = {(p["day"], p["decision_bar"]): p for p in buy_preds}
    sell_map = {(p["day"], p["decision_bar"]): p for p in sell_preds}
    keys = sorted(set(buy_map) | set(sell_map))
    decisions = []
    for k in keys:
        b = buy_map.get(k)
        s = sell_map.get(k)
        b_stress = stress_ev_proxy(b) if b else None
        s_stress = stress_ev_proxy(s) if s else None
        d = decide(b, s, buy_stress_ev=b_stress, sell_stress_ev=s_stress)
        # Realized net_r of chosen action for diagnostics (not used to tune)
        realized = None
        if d["decision"] == "BUY" and b is not None:
            realized = b.get("actual_net_r")
        elif d["decision"] == "SELL" and s is not None:
            realized = s.get("actual_net_r")
        elif d["decision"] == "WAIT":
            realized = 0.0
        decisions.append(
            {
                "day": k[0],
                "decision_bar": k[1],
                "decision": d["decision"],
                "reason": d["reason"],
                "selected_ev": d.get("selected_ev"),
                "realized_net_r": realized,
                "detail": d["detail"],
            }
        )
    return decisions


def decision_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter

    c = Counter(d["decision"] for d in decisions)
    realized = [float(d["realized_net_r"]) for d in decisions if d.get("realized_net_r") is not None]
    reject_reasons: Counter[str] = Counter()
    for d in decisions:
        for side in ("buy", "sell"):
            block = (d.get("detail") or {}).get(side) or {}
            if block and not block.get("eligible"):
                for r in block.get("reasons") or []:
                    reject_reasons[f"{side}:{r}"] += 1
    return {
        "n": len(decisions),
        "decision_counts": dict(c),
        "wait_rate": (c.get("WAIT", 0) / len(decisions)) if decisions else None,
        "mean_realized_net_r": (sum(realized) / len(realized)) if realized else None,
        "rejection_reason_counts": dict(reject_reasons),
        "thresholds_frozen": POLICY_THRESHOLDS,
    }
