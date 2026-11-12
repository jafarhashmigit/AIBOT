"""Three preregistered decision families — BUY/SELL/WAIT with costed economics."""

from __future__ import annotations

from typing import Any

from phase53.constants import (
    CMC_MAX_SPREAD_ATR,
    CMC_MIN_ABS_DISP_ATR,
    EXF_MAX_IMPULSE_RETR,
    EXF_MAX_SPREAD_ATR,
    EXF_MIN_ABS_CONSEC,
    SLF_MAX_SPREAD_DELTA,
    SLF_REQUIRE_OVERLAP,
    canonical_json_sha256,
)


def family_registry() -> dict[str, Any]:
    families = [
        {
            "family_id": "F1_CMC",
            "name": "Costed Momentum Continuation",
            "economic_rationale": (
                "Volatility-adjusted 12-bar displacement indicates short-horizon continuation. "
                "Trade only during London/NY overlap when |disp|/ATR exceeds a half-ATR threshold "
                "and spread/ATR is below a fixed cost gate — otherwise WAIT is the economic choice."
            ),
            "categories": ["volatility_adjusted_displacement", "bid_ask_execution", "session"],
            "features": ["B02_net_disp_atr_12", "E02_spread_atr", "D03_overlap", "C02_rv_48"],
            "thresholds": {
                "min_abs_disp_atr": CMC_MIN_ABS_DISP_ATR,
                "max_spread_atr": CMC_MAX_SPREAD_ATR,
                "require_overlap": True,
            },
            "retired_not_used": ["H13_C", "mean_reversion", "phase50_learner", "phase51_learner"],
        },
        {
            "family_id": "F2_EXF",
            "name": "Persistence Exhaustion Fade",
            "economic_rationale": (
                "Long same-direction close streaks with fading impulse/retracement ratio suggest "
                "exhaustion. Fade the streak when spread/ATR remains tradable; otherwise WAIT."
            ),
            "categories": ["trend_persistence_vs_exhaustion", "bid_ask_execution"],
            "features": ["B03_consec_dir", "B04_impulse_retr_ratio", "E02_spread_atr", "C02_rv_48"],
            "thresholds": {
                "min_abs_consec": EXF_MIN_ABS_CONSEC,
                "max_impulse_retr": EXF_MAX_IMPULSE_RETR,
                "max_spread_atr": EXF_MAX_SPREAD_ATR,
            },
            "retired_not_used": ["H13_C", "mean_reversion", "phase42", "phase44"],
        },
        {
            "family_id": "F3_SLF",
            "name": "Session Liquidity MTF Filter",
            "economic_rationale": (
                "Multi-timeframe agreement is informative only in the liquid London/NY overlap and "
                "when spread is not expanding vs recent median. Direction follows completed H1 return; "
                "otherwise WAIT."
            ),
            "categories": ["session_dependent", "regime_state", "bid_ask_execution"],
            "features": ["D03_overlap", "F04_mtf_agree", "F02_h1_ret", "E03_spread_delta", "C02_rv_48"],
            "thresholds": {
                "require_overlap": SLF_REQUIRE_OVERLAP,
                "max_spread_delta": SLF_MAX_SPREAD_DELTA,
                "require_mtf_agree": 1.0,
            },
            "retired_not_used": ["phase49_failed_hypotheses"],
        },
    ]
    reg = {
        "n_families": len(families),
        "max_families": 3,
        "one_policy_per_family": True,
        "no_parameter_search": True,
        "families": families,
    }
    reg["registry_sha256"] = canonical_json_sha256({k: v for k, v in reg.items() if k != "registry_sha256"})
    return reg


def _ood(feats: dict[str, Any], ood_bounds: dict[str, Any] | None) -> bool:
    if not ood_bounds:
        return False
    v = feats.get("C02_rv_48")
    if v is None:
        return True
    lo, hi = ood_bounds.get("C02_lo"), ood_bounds.get("C02_hi")
    if lo is None or hi is None:
        return False
    return float(v) < float(lo) or float(v) > float(hi)


def decide_cmc(feats: dict[str, Any], *, ood_bounds: dict[str, Any] | None = None) -> dict[str, Any]:
    if _ood(feats, ood_bounds):
        return {"action": "WAIT", "reason": "ood_vol_regime", "family_id": "F1_CMC"}
    b02 = feats.get("B02_net_disp_atr_12")
    e02 = feats.get("E02_spread_atr")
    d03 = feats.get("D03_overlap")
    if b02 is None or e02 is None or d03 is None:
        return {"action": "WAIT", "reason": "missing_feature", "family_id": "F1_CMC"}
    if float(d03) < 1.0:
        return {"action": "WAIT", "reason": "outside_overlap_session", "family_id": "F1_CMC"}
    if float(e02) > CMC_MAX_SPREAD_ATR:
        return {"action": "WAIT", "reason": "spread_cost_gate", "family_id": "F1_CMC"}
    if abs(float(b02)) < CMC_MIN_ABS_DISP_ATR:
        return {"action": "WAIT", "reason": "insufficient_displacement", "family_id": "F1_CMC"}
    action = "BUY" if float(b02) > 0 else "SELL"
    return {"action": action, "reason": "costed_momentum", "family_id": "F1_CMC", "signal": float(b02)}


def decide_exf(feats: dict[str, Any], *, ood_bounds: dict[str, Any] | None = None) -> dict[str, Any]:
    if _ood(feats, ood_bounds):
        return {"action": "WAIT", "reason": "ood_vol_regime", "family_id": "F2_EXF"}
    b03 = feats.get("B03_consec_dir")
    b04 = feats.get("B04_impulse_retr_ratio")
    e02 = feats.get("E02_spread_atr")
    if b03 is None or b04 is None or e02 is None:
        return {"action": "WAIT", "reason": "missing_feature", "family_id": "F2_EXF"}
    if float(e02) > EXF_MAX_SPREAD_ATR:
        return {"action": "WAIT", "reason": "spread_cost_gate", "family_id": "F2_EXF"}
    if abs(float(b03)) < EXF_MIN_ABS_CONSEC:
        return {"action": "WAIT", "reason": "no_persistence_extremum", "family_id": "F2_EXF"}
    if float(b04) >= EXF_MAX_IMPULSE_RETR:
        return {"action": "WAIT", "reason": "impulse_still_strong", "family_id": "F2_EXF"}
    # Fade the streak
    action = "SELL" if float(b03) > 0 else "BUY"
    return {"action": action, "reason": "exhaustion_fade", "family_id": "F2_EXF", "signal": float(b03)}


def decide_slf(feats: dict[str, Any], *, ood_bounds: dict[str, Any] | None = None) -> dict[str, Any]:
    if _ood(feats, ood_bounds):
        return {"action": "WAIT", "reason": "ood_vol_regime", "family_id": "F3_SLF"}
    d03 = feats.get("D03_overlap")
    f04 = feats.get("F04_mtf_agree")
    f02 = feats.get("F02_h1_ret")
    e03 = feats.get("E03_spread_delta")
    if SLF_REQUIRE_OVERLAP and (d03 is None or float(d03) < 1.0):
        return {"action": "WAIT", "reason": "outside_overlap_session", "family_id": "F3_SLF"}
    if f04 is None or f02 is None or e03 is None:
        return {"action": "WAIT", "reason": "missing_mtf_or_spread", "family_id": "F3_SLF"}
    if float(f04) < 1.0:
        return {"action": "WAIT", "reason": "mtf_not_agreeing", "family_id": "F3_SLF"}
    if float(e03) > SLF_MAX_SPREAD_DELTA:
        return {"action": "WAIT", "reason": "spread_expanding", "family_id": "F3_SLF"}
    if float(f02) > 0:
        return {"action": "BUY", "reason": "session_mtf_agree_up", "family_id": "F3_SLF", "signal": float(f02)}
    if float(f02) < 0:
        return {"action": "SELL", "reason": "session_mtf_agree_down", "family_id": "F3_SLF", "signal": float(f02)}
    return {"action": "WAIT", "reason": "flat_h1", "family_id": "F3_SLF"}


DECISION_FNS = {
    "F1_CMC": decide_cmc,
    "F2_EXF": decide_exf,
    "F3_SLF": decide_slf,
}


def fit_ood_bounds(events: list[dict[str, Any]]) -> dict[str, float]:
    """Single discovery freeze of vol IQR for OOD WAIT — not a parameter search."""
    vals = [float(e["features"]["C02_rv_48"]) for e in events if e["features"].get("C02_rv_48") is not None]
    if len(vals) < 20:
        return {}
    vs = sorted(vals)
    n = len(vs)
    q1 = vs[n // 4]
    q3 = vs[(3 * n) // 4]
    iqr = q3 - q1
    return {"C02_lo": q1 - 1.5 * iqr, "C02_hi": q3 + 1.5 * iqr, "n": float(n)}


def apply_policy(
    events: list[dict[str, Any]],
    family_id: str,
    *,
    ood_bounds: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fn = DECISION_FNS[family_id]
    out = []
    for e in sorted(events, key=lambda x: (x["day"], x["decision_idx"])):
        dec = fn(e["features"], ood_bounds=ood_bounds)
        action = dec["action"]
        if action == "WAIT":
            net_r = 0.0
            stress_r = 0.0
            quality = "WAIT"
        else:
            oc = e["buy"] if action == "BUY" else e["sell"]
            net_r = float(oc["net_r"]) if oc.get("net_r") is not None else None
            sn = (oc.get("scenario_nets") or {}).get("STRESS_SPREAD_WIDEN_1_5X") or {}
            stress_r = float(sn["net_r"]) if sn.get("net_r") is not None else None
            quality = oc.get("data_quality_status")
        out.append(
            {
                "day": e["day"],
                "decision_bar": e["decision_bar"],
                "decision_idx": e["decision_idx"],
                "family_id": family_id,
                "action": action,
                "reason": dec.get("reason"),
                "net_r": net_r,
                "stress_net_r": stress_r,
                "data_quality_status": quality,
                "ood": dec.get("reason") == "ood_vol_regime",
            }
        )
    return out
