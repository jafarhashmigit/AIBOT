"""Preregistered evidence sufficiency — thresholds fixed before outcome analysis."""

from __future__ import annotations

from typing import Any

from phase61.constants import SUFFICIENCY_THRESHOLDS, canonical_json_sha256


def assess_sufficiency(
    *,
    n_independent_decisions: int,
    n_actual_fills: int,
    n_trading_days: int,
    sessions_represented: int,
    missing_record_rate: float | None,
    account_consistent: bool,
    volume_consistent: bool,
) -> dict[str, Any]:
    thr = dict(SUFFICIENCY_THRESHOLDS)
    checks = {
        "independent_decisions": n_independent_decisions >= thr["min_independent_decisions"],
        "actual_fills": n_actual_fills >= thr["min_actual_fills"],
        "trading_days": n_trading_days >= thr["min_trading_days"],
        "sessions": sessions_represented >= thr["min_sessions_represented"],
        "missing_rate": (missing_record_rate is not None and missing_record_rate <= thr["max_missing_record_rate"]),
        "account_consistent": account_consistent,
        "volume_consistent": volume_consistent,
    }
    sufficient = all(checks.values())
    out = {
        "preregistered_thresholds": thr,
        "thresholds_chosen_before_outcome_analysis": True,
        "observed": {
            "n_independent_decisions": n_independent_decisions,
            "n_actual_fills": n_actual_fills,
            "n_trading_days": n_trading_days,
            "sessions_represented": sessions_represented,
            "missing_record_rate": missing_record_rate,
            "account_consistent": account_consistent,
            "volume_consistent": volume_consistent,
        },
        "checks": checks,
        "sufficient_for_stable_live_economics_claim": False,  # never claim live from demo/small samples here
        "sufficient_for_account_specific_cost_model": sufficient and account_consistent,
        "dependence_note": (
            "Multiple fills from one order / multiple orders from one market event are not independent observations"
        ),
        "small_demo_sample_establishes_live_economics": False,
        "confidence_intervals": "Not claimed without adequate independent fills",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
