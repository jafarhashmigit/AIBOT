"""Final data-quality verdict (separate from provider / MT5 / licensing)."""

from __future__ import annotations

from typing import Any

from phase34.constants import (
    CHAMPION_STATUS,
    H13_C_STATUS,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
)
from phase34.progress import write_json


def finalize(
    *,
    acquisition: dict[str, Any],
    quality: dict[str, Any],
    dst: dict[str, Any],
    spreads: dict[str, Any],
    costs: dict[str, Any],
    intrabar: dict[str, Any],
    mt5: dict[str, Any],
    immutability: dict[str, Any],
    independent: dict[str, Any],
) -> dict[str, Any]:
    n_complete = int(acquisition.get("n_complete_trading_days") or 0)
    n_ticks = int((acquisition.get("totals") or {}).get("ticks") or 0)
    quality_ok = bool(quality.get("pass"))
    dst_ok = bool(dst.get("pass"))
    spread_ok = bool(spreads.get("pass"))
    indep_ok = False
    if independent and spreads.get("overall_usd"):
        med_a = spreads["overall_usd"].get("median")
        med_b = independent.get("median")
        if med_a is not None and med_b is not None:
            indep_ok = abs(med_a - med_b) < 1e-9 or abs(med_a - med_b) / max(abs(med_a), 1e-12) < 1e-6

    # Verdicts
    if quality_ok and dst_ok and spread_ok and n_complete >= 10 and n_ticks >= 500_000 and indep_ok:
        verdict = "EXTENDED_HISTORICAL_BID_ASK_QUALITY_PASS"
    elif quality_ok and n_ticks > 0 and (n_complete >= 3 or n_ticks >= 100_000):
        verdict = "PARTIAL_HISTORICAL_BID_ASK_QUALITY"
    else:
        verdict = "HISTORICAL_DATA_QUALITY_FAIL"

    # Soften PASS if DST confidence low or wall budget stopped early with few complete days
    if verdict == "EXTENDED_HISTORICAL_BID_ASK_QUALITY_PASS":
        if acquisition.get("stopped_early") and n_complete < 15:
            verdict = "PARTIAL_HISTORICAL_BID_ASK_QUALITY"
        if dst.get("unqualified_periods"):
            verdict = "PARTIAL_HISTORICAL_BID_ASK_QUALITY"

    license_status = {
        "status": "RESEARCH_PERSONAL_USE_REVIEWED_COMMERCIAL_NOT_CLEARED",
        "commercial_permission_claimed": False,
        "redistribution": "not_authorized_by_this_phase",
        "evidence_class": "OFFICIALLY_DOCUMENTED_PARTIAL_FROM_PRIOR_PHASES",
    }

    provider_qualification = {
        "note": "Provider qualification remains separate from Phase34 data-quality verdict.",
        "historical_bid_ask_qualified": False,
        "reason": "Licensing + MT5 parity + full execution realism criteria not all met.",
    }

    report = {
        "recipe_id": RECIPE_ID,
        "final_verdict": verdict,
        "provider_qualification": provider_qualification,
        "mt5_parity_status": mt5.get("status"),
        "license_status": license_status,
        "gates": {
            "n_complete_trading_days": n_complete,
            "n_ticks": n_ticks,
            "quality_pass": quality_ok,
            "dst_pass": dst_ok,
            "spread_pass": spread_ok,
            "independent_recompute_ok": indep_ok,
            "phase33_immutable": immutability.get("phase33_immutable_ok"),
            "protected_intact": immutability.get("protected_artifacts_intact"),
        },
        "intrabar_classification": intrabar.get("classification"),
        "cost_recommendation": costs.get("recommendation"),
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "h13_c": H13_C_STATUS,
        "strategy_evaluated": False,
        "labels_modified": False,
    }
    write_json("final_qualification.json", report)
    return report
