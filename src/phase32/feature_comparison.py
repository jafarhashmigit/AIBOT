"""Compare independent features vs stored Phase1 / UTC-corrected artifacts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from phase32.constants import (
    FEATURES_PATH,
    FEATURES_UTC_PATH,
    FEATURE_TOL_ABS,
    FEATURE_TOL_REL,
    HOLDOUT_NAME,
    RESEARCH_CUTOFF_UTC,
)


def _match_stats(a: np.ndarray, b: np.ndarray, *, abs_tol: float, rel_tol: float) -> dict[str, Any]:
    both_nan = np.isnan(a) & np.isnan(b)
    either_nan = np.isnan(a) | np.isnan(b)
    comparable = ~either_nan
    abs_diff = np.full(len(a), np.nan)
    abs_diff[comparable] = np.abs(a[comparable] - b[comparable])
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = abs_diff / np.maximum(np.abs(b), 1e-12)
    exact = comparable & (a == b)
    tol = comparable & ((abs_diff <= abs_tol) | (rel <= rel_tol))
    mismatch = comparable & ~tol
    return {
        "n": int(len(a)),
        "both_nan": int(both_nan.sum()),
        "nan_disagree": int((either_nan & ~both_nan).sum()),
        "exact_match": int(exact.sum()),
        "tol_match": int(tol.sum()),
        "mismatch": int(mismatch.sum()),
        "max_abs_diff": float(np.nanmax(abs_diff)) if comparable.any() else None,
        "mismatch_pct": float(mismatch.mean()) if len(a) else None,
    }


def compare_features(independent: pd.DataFrame, corrected: pd.DataFrame) -> dict[str, Any]:
    if HOLDOUT_NAME in str(FEATURES_PATH):
        raise RuntimeError("HARD FAILURE: holdout path referenced")
    stored = pd.read_csv(FEATURES_PATH)
    stored["time"] = pd.to_datetime(stored["time"])
    ind = independent.copy()
    ind["time"] = pd.to_datetime(ind["time"])
    ind = ind.set_index("time").sort_index()
    ref = stored.set_index("time").sort_index()
    common = ind.index.intersection(ref.index)

    skip = {"time_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"}
    cols = sorted((set(ind.columns) & set(ref.columns)) - skip)

    per_feature = {}
    worst = []
    for c in cols:
        a = pd.to_numeric(ind.loc[common, c], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(ref.loc[common, c], errors="coerce").to_numpy(dtype=float)
        st = _match_stats(a, b, abs_tol=FEATURE_TOL_ABS, rel_tol=FEATURE_TOL_REL)
        per_feature[c] = st
        if st["mismatch"]:
            abs_diff = np.abs(a - b)
            mask = np.isfinite(abs_diff)
            if mask.any():
                i = int(np.nanargmax(np.where(mask, abs_diff, -1.0)))
                worst.append(
                    {
                        "feature": c,
                        "time": str(common[i]),
                        "ind": float(a[i]) if np.isfinite(a[i]) else None,
                        "ref": float(b[i]) if np.isfinite(b[i]) else None,
                        "abs_diff": float(abs_diff[i]),
                    }
                )

    # UTC corrected columns on research cutoff slice
    utc_stored = pd.read_csv(FEATURES_UTC_PATH)
    utc_stored["time"] = pd.to_datetime(utc_stored["time"])
    corr = corrected.copy()
    corr["time"] = pd.to_datetime(corr["time"])
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)
    corr = corr[corr["time"] <= cutoff].set_index("time").sort_index()
    uref = utc_stored.set_index("time").sort_index()
    common2 = corr.index.intersection(uref.index)
    corrected_cols = [
        "corrected_hour_utc",
        "corrected_weekday_utc",
        "corrected_session_asia",
        "corrected_session_london",
        "corrected_session_new_york",
        "corrected_session_london_ny_overlap",
        "corrected_session_id",
        "corrected_time_utc",
    ]
    corr_stats = {}
    for c in corrected_cols:
        if c not in corr.columns or c not in uref.columns:
            corr_stats[c] = {"status": "UNVERIFIED", "reason": "column missing"}
            continue
        if c == "corrected_time_utc":
            a_s = corr.loc[common2, c].astype(str).to_numpy()
            b_s = uref.loc[common2, c].astype(str).to_numpy()
            mism = int((a_s != b_s).sum())
            corr_stats[c] = {
                "n": int(len(common2)),
                "exact_match": int(len(common2) - mism),
                "mismatch": mism,
                "mismatch_pct": mism / len(common2) if len(common2) else None,
            }
            continue
        a = pd.to_numeric(corr.loc[common2, c], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(uref.loc[common2, c], errors="coerce").to_numpy(dtype=float)
        corr_stats[c] = _match_stats(a, b, abs_tol=0, rel_tol=0)

    total_exact = sum(v.get("exact_match", 0) for v in per_feature.values())
    total_tol = sum(v.get("tol_match", 0) for v in per_feature.values())
    total_mis = sum(v.get("mismatch", 0) for v in per_feature.values())
    total_comp = sum(
        v["n"] - v.get("both_nan", 0) - v.get("nan_disagree", 0) for v in per_feature.values()
    )
    worst = sorted(worst, key=lambda x: x["abs_diff"], reverse=True)[:15]
    corr_ok = all(v.get("mismatch", 1) == 0 for v in corr_stats.values() if "mismatch" in v)

    return {
        "holdout_opened": False,
        "joined_rows_vs_features_csv": int(len(common)),
        "joined_rows_vs_utc_corrected": int(len(common2)),
        "n_features_compared": len(per_feature),
        "feature_by_feature": per_feature,
        "corrected_utc_by_feature": corr_stats,
        "totals": {
            "exact_match_count": total_exact,
            "tol_match_count": total_tol,
            "mismatch_count": total_mis,
            "comparable_cells": total_comp,
            "mismatch_pct": (total_mis / total_comp) if total_comp else None,
        },
        "worst_mismatches": worst,
        "all_features_match_within_tol": total_mis == 0,
        "corrected_utc_match": corr_ok,
    }
