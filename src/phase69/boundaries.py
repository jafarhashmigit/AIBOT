"""Research boundaries — data separation."""

from __future__ import annotations

from typing import Any

from phase65.consumption import build_consumption_registry
from phase69.constants import canonical_json_sha256


def research_boundaries() -> dict[str, Any]:
    cons = build_consumption_registry()
    out = {
        "stores": [
            {"name": "consumed_metaquotes_archive", "symbol": "XAUUSD", "use": "exploratory/engineering_only"},
            {"name": "exness_live_journal", "symbol": "XAUUSDm", "use": "independent_live_evidence"},
            {"name": "synthetic_fixtures", "use": "tests_only_separate_store"},
            {"name": "historical_hypothetical_experience", "use": "separate_from_paper"},
            {"name": "aibot_paper_decision_experience", "use": "separate_from_hypothetical"},
        ],
        "do_not_combine_xauusd_with_xauusdm": True,
        "phase58_holdout_sealed": cons["phase58_holdout_sealed"],
        "phase58_holdout_opened": cons["phase58_holdout_opened"],
        "consumed_archive_as_confirmation": False,
        "relabel_resample_threshold_change_creates_independence": False,
        "methodology_for_future_tests": [
            "Date-blocked discovery and validation",
            "Date-level bootstrap CIs",
            "Dependence and overlapping-event controls",
            "Multiple-testing correction",
            "Out-of-sample / walk-forward where appropriate",
            "Gross vs net separation",
            "Sensitivity to spread/commission/swap/slippage assumptions",
            "Compare vs WAIT and simple baselines",
            "Unknown costs remain UNKNOWN — never zero",
        ],
        "strategy_promotion_in_phase69": False,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
