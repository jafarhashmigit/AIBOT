"""Report writers and MFE/MAE join for H13_C trades."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from phase27.constants import RECIPE_ID, REPORTS_DIR


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


def join_mfe_mae(trades: list[dict], m5: dict, outcomes26: dict) -> list[dict]:
    """Attach research MFE/MAE (BUY/SELL path) at H=12 for retrospective analysis."""
    idx_map = m5["index"]
    out = []
    for t in trades:
        row = dict(t)
        i = idx_map.get(t["decision_time"])
        side = t["side"]
        if i is None:
            row["mfe_12_atr"] = None
            row["mae_12_atr"] = None
            row["mfe_mae_ratio"] = None
        else:
            if side == "BUY":
                mfe = outcomes26["mfe_buy_atr"][12][i]
                mae = outcomes26["mae_buy_atr"][12][i]
            else:
                mfe = outcomes26["mfe_sell_atr"][12][i]
                mae = outcomes26["mae_sell_atr"][12][i]
            row["mfe_12_atr"] = float(mfe) if np.isfinite(mfe) else None
            row["mae_12_atr"] = float(mae) if np.isfinite(mae) else None
            if row["mfe_12_atr"] is not None and row["mae_12_atr"] not in (None, 0):
                row["mfe_mae_ratio"] = row["mfe_12_atr"] / max(row["mae_12_atr"], 1e-12)
            else:
                row["mfe_mae_ratio"] = None
        out.append(row)
    return out


def mfe_mae_by_regime(trades: list[dict]) -> dict[str, Any]:
    out = {}
    for reg in ("low", "medium", "high"):
        rows = [t for t in trades if t.get("pred_vol_regime") == reg]
        mfes = [t["mfe_12_atr"] for t in rows if t.get("mfe_12_atr") is not None]
        maes = [t["mae_12_atr"] for t in rows if t.get("mae_12_atr") is not None]
        ratios = [t["mfe_mae_ratio"] for t in rows if t.get("mfe_mae_ratio") is not None]
        out[reg] = {
            "n": len(rows),
            "mfe_mean": float(np.mean(mfes)) if mfes else None,
            "mae_mean": float(np.mean(maes)) if maes else None,
            "mfe_mae_ratio_mean": float(np.mean(ratios)) if ratios else None,
        }
    return {
        "by_regime": out,
        "note": "MFE/MAE are Phase 26 research labels (ATR units), not H13_C net R.",
    }


def write_reports(
    *,
    summary: dict,
    vol_audit: dict,
    regime: dict,
    policies: dict,
    stats: dict,
    safety: dict,
) -> dict[str, str]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}

    def dump(name: str, payload: dict) -> None:
        p = REPORTS_DIR / name
        p.write_text(json.dumps(_sanitize(payload), indent=2), encoding="utf-8")
        paths[name] = str(p)

    dump("phase27_summary.json", summary)
    dump("volatility_prediction_audit.json", vol_audit)
    dump("h13c_regime_analysis.json", regime)
    dump("hypothetical_policy_comparison.json", policies)
    dump("statistical_validation.json", stats)
    dump("safety_audit.json", safety)
    return paths


def build_summary(
    *,
    preflight: dict,
    verdict: dict,
    vol_audit: dict,
    policies: dict,
    answers: dict,
) -> dict:
    return {
        "report": "phase27_summary",
        "recipe": RECIPE_ID,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preflight": preflight,
        "verdict": verdict,
        "vol_prediction_headline": {
            "n_folds_improved": vol_audit.get("n_folds_improved"),
            "all_folds_improved": vol_audit.get("all_folds_improved"),
        },
        "policy_headline": {
            k: {
                "n": v["n"],
                "mean_r": v["mean_r"],
                "delta_mean_r_vs_baseline": v.get("delta_mean_r_vs_baseline"),
            }
            for k, v in policies["policies"].items()
        },
        "decision_quality_answers": answers,
        "trading_edge_claimed": False,
    }
