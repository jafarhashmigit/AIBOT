"""Assemble Phase 26 comparative evaluation and verdict."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from phase26.constants import (
    CHAMPION_STATUS,
    H13C_STATUS,
    HORIZONS,
    PHASE25_VERDICT,
    PRODUCTION_FINAL_ACTION,
    RECIPE_ID,
    REPORTS_DIR,
    VALID_VERDICTS,
)


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if v != v else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def outcome_quality_summary(outcomes: dict, decision_indices: list[int]) -> dict[str, Any]:
    summary = {"horizons": {}, "notes": [
        "MFE/MAE are ATR-normalized price excursions after next-bar entry, not net realized R.",
        "Eligible windows exclude gaps (is_after_gap) and minute gaps > 10.",
        "Favorable-before-adverse uses FAV_ATR=0.5 and ADV_ATR=0.5 on BUY path.",
    ]}
    for H in HORIZONS:
        elig = outcomes["eligible"][H]
        idx = [i for i in decision_indices if elig[i] == 1.0]
        if not idx:
            summary["horizons"][str(H)] = {"n_eligible": 0}
            continue
        mfe = outcomes["mfe_buy_atr"][H][idx]
        mae = outcomes["mae_buy_atr"][H][idx]
        fba = outcomes["fav_before_adv_buy"][H][idx]
        neither = outcomes["neither_buy"][H][idx]
        summary["horizons"][str(H)] = {
            "n_eligible": len(idx),
            "mfe_buy_mean": float(np.nanmean(mfe)),
            "mae_buy_mean": float(np.nanmean(mae)),
            "fav_before_adv_rate": float(np.nanmean(fba)) if np.any(np.isfinite(fba)) else None,
            "neither_rate": float(np.nanmean(neither)) if np.any(np.isfinite(neither)) else None,
            "fwd_vol_mean": float(np.nanmean(outcomes["fwd_vol"][H][idx])),
            "fwd_ret_buy_mean": float(np.nanmean(outcomes["fwd_ret_buy"][H][idx])),
        }
    return summary


def decide_verdict(redundancy: dict, wf: dict) -> dict[str, Any]:
    accepted = redundancy.get("accepted") or []
    if not accepted:
        verdict = "NO_INCREMENTAL_INFORMATION"
        why = "No orthogonal candidates survived the predeclared redundancy gate."
    else:
        # count targets with improvement on >=2 folds
        strong = 0
        any_imp = 0
        for tid, block in wf.items():
            n_imp = int(block.get("n_folds_improved") or 0)
            if n_imp >= 1:
                any_imp += 1
            if n_imp >= 2:
                strong += 1
            if block.get("all_folds_improved"):
                strong += 1
        if strong >= 2:
            verdict = "PROMISING_BUT_UNCONFIRMED"
            why = (
                "Accepted orthogonal features improved predictive metrics on multiple "
                "targets/folds, but this is not a trading-edge claim and is not production-ready."
            )
        elif any_imp >= 1:
            verdict = "PREDICTIVE_IMPROVEMENT_ONLY"
            why = (
                "Some predictive metrics improved with accepted features, but improvements "
                "are not consistently confirmed across folds/targets; no trading promotion."
            )
        else:
            verdict = "NO_INCREMENTAL_INFORMATION"
            why = (
                "Accepted features exist mathematically, but walk-forward predictive "
                "baselines show no reliable incremental improvement."
            )

    assert verdict in VALID_VERDICTS
    # Never auto-promote to CANDIDATE without explicit economic + predictive consistency;
    # Phase 26 does not evaluate trading PnL of new features as a strategy.
    return {
        "verdict": verdict,
        "rationale": why,
        "production_ready": False,
        "champion_status": CHAMPION_STATUS,
        "h13c_status": H13C_STATUS,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "phase25_verdict_preserved": PHASE25_VERDICT,
        "accepted_feature_count": len(accepted),
    }


def write_reports(
    *,
    redundancy: dict,
    outcome_quality: dict,
    walk_forward: dict,
    safety: dict,
    verdict: dict,
    preflight: dict,
) -> dict[str, str]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}

    def dump(name: str, payload: dict) -> str:
        p = REPORTS_DIR / name
        p.write_text(json.dumps(_sanitize(payload), indent=2), encoding="utf-8")
        paths[name] = str(p)
        return str(p)

    dump("feature_redundancy.json", redundancy)
    dump("outcome_quality.json", outcome_quality)
    dump("walk_forward_results.json", walk_forward)
    dump("safety_audit.json", safety)

    summary = {
        "report": "phase26_summary",
        "recipe": RECIPE_ID,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preflight": preflight,
        "verdict": verdict,
        "accepted_features": redundancy.get("accepted"),
        "rejected_features": redundancy.get("rejected"),
        "walk_forward_headline": {
            tid: {
                "n_folds_improved": walk_forward[tid]["n_folds_improved"],
                "all_folds_improved": walk_forward[tid]["all_folds_improved"],
            }
            for tid in walk_forward
        },
        "multiple_testing_note": (
            "Feature candidates, redundancy threshold, targets, and model families were "
            "predeclared before evaluation. Single confirmatory pass; no iterative retuning."
        ),
        "trading_edge_claimed": False,
    }
    dump("phase26_summary.json", summary)
    return paths
