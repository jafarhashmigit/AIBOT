"""Phase47 verdict selection — honest about calibration sufficiency."""

from __future__ import annotations

from typing import Any

from phase47.constants import POLICY_THRESHOLDS


def choose_verdict(payload: dict[str, Any]) -> tuple[str, str]:
    if not payload.get("preflight", {}).get("ok"):
        return "DATA_INTEGRITY_FAILURE", "Phase46 full integrity verification failed."

    buy_cal = payload.get("buy_calibration") or {}
    sell_cal = payload.get("sell_calibration") or {}
    policy = payload.get("policy_summary") or {}
    th = POLICY_THRESHOLDS

    n_buy = int(buy_cal.get("n") or 0)
    n_sell = int(sell_cal.get("n") or 0)
    ece_buy = (buy_cal.get("calibration") or {}).get("ece")
    ece_sell = (sell_cal.get("calibration") or {}).get("ece")
    min_n = int(th["min_oof_samples_for_calibration_claim"])
    max_ece = float(th["max_ece_for_sufficient_calibration"])

    engine_built = bool(payload.get("engine_implemented"))
    if not engine_built:
        return "DECISION_POLICY_NOT_READY", "Decision engine components incomplete."

    # EV reliability: if predicted EV has near-zero/negative correlation and large error
    buy_corr = (buy_cal.get("ev_decomp_error") or {}).get("corr")
    sell_corr = (sell_cal.get("ev_decomp_error") or {}).get("corr")
    ev_unreliable = False
    if buy_corr is not None and sell_corr is not None:
        if (buy_corr is not None and buy_corr < 0.05) and (sell_corr is not None and sell_corr < 0.05):
            ev_unreliable = True

    cal_insufficient = False
    reasons = []
    if n_buy < min_n or n_sell < min_n:
        cal_insufficient = True
        reasons.append(f"oof_n_below_{min_n} (buy={n_buy}, sell={n_sell})")
    if ece_buy is not None and ece_buy > max_ece:
        cal_insufficient = True
        reasons.append(f"buy_ece={ece_buy:.4f}>{max_ece}")
    if ece_sell is not None and ece_sell > max_ece:
        cal_insufficient = True
        reasons.append(f"sell_ece={ece_sell:.4f}>{max_ece}")

    # Prefer honest calibration/EV verdicts over claiming readiness for production
    if ev_unreliable and cal_insufficient:
        return (
            "EV_ESTIMATION_UNRELIABLE",
            "OOF expected-value estimates show weak association with realized net R; "
            + "; ".join(reasons),
        )
    if cal_insufficient:
        return (
            "CALIBRATION_INSUFFICIENT",
            "Decision engine implemented but calibration is not reliable on exposed engineering dates: "
            + "; ".join(reasons),
        )
    if ev_unreliable:
        return (
            "EV_ESTIMATION_UNRELIABLE",
            "Calibration metrics pass gates but EV prediction association with realized net R is weak.",
        )

    wait_rate = policy.get("wait_rate")
    if wait_rate is None:
        return "DECISION_POLICY_NOT_READY", "Policy decisions missing."

    return (
        "DECISION_ENGINE_IMPLEMENTED",
        (
            "Calibrated decision interfaces, EV decomposition, OOD/uncertainty gates, and intelligent WAIT "
            "are implemented and independently verified. Results remain EXPLORATORY on exposed dates; "
            "Champion=NO_MODEL, Production=WAIT. Not a profitability claim."
        ),
    )
