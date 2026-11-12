"""Feature redundancy / incremental information vs baseline store."""

from __future__ import annotations

from typing import Any

import numpy as np

from phase26.constants import (
    BASELINE_FEATURE_COLS,
    ORTHOGONAL_CANDIDATES,
    REDUNDANCY_CORR_MAX,
)
from phase26.data import train_cutoff_for_fold
from phase26.features import FEATURE_FORMULAS


def _baseline_matrix(m5: dict, idx: np.ndarray) -> np.ndarray:
    rows = m5["rows"]
    cols = []
    for j in idx:
        row = rows[int(j)]
        cols.append([float(row[c]) for c in BASELINE_FEATURE_COLS])
    return np.asarray(cols, dtype=float)


def analyze_redundancy(
    m5: dict,
    feats: dict[str, np.ndarray],
    *,
    fold_id: str = "WF1",
) -> dict[str, Any]:
    """Use only pre-fold training timestamps (before purge cutoff) for redundancy."""
    cutoff = train_cutoff_for_fold(fold_id)
    times = m5["times"]
    train_idx = [i for i, t in enumerate(times) if t <= cutoff]
    # subsample for speed / stability
    if len(train_idx) > 8000:
        train_idx = train_idx[:: max(1, len(train_idx) // 8000)]
    idx = np.asarray(train_idx, dtype=int)

    B = _baseline_matrix(m5, idx)
    # drop rows with nan in baseline
    mask = np.all(np.isfinite(B), axis=1)
    idx = idx[mask]
    B = B[mask]

    accepted = []
    rejected = []
    details = {}

    for name in ORTHOGONAL_CANDIDATES:
        x = feats[name][idx]
        m = np.isfinite(x)
        if m.sum() < 200:
            rejected.append(name)
            details[name] = {
                "status": "REJECTED",
                "reason": "insufficient_finite_train_samples",
                "n": int(m.sum()),
                "formula": FEATURE_FORMULAS.get(name),
            }
            continue
        xx = x[m]
        BB = B[m]
        corrs = []
        for k, base in enumerate(BASELINE_FEATURE_COLS):
            b = BB[:, k]
            if float(np.std(b)) < 1e-15 or float(np.std(xx)) < 1e-15:
                corrs.append((base, 0.0))
                continue
            corrs.append((base, float(np.corrcoef(xx, b)[0, 1])))
        corrs.sort(key=lambda t: abs(t[1]), reverse=True)
        top_name, top_corr = corrs[0]
        if abs(top_corr) >= REDUNDANCY_CORR_MAX:
            rejected.append(name)
            details[name] = {
                "status": "REJECTED",
                "reason": "redundant_vs_baseline",
                "max_abs_corr": top_corr,
                "max_corr_feature": top_name,
                "top5": corrs[:5],
                "formula": FEATURE_FORMULAS.get(name),
                "warmup_note": "see FEATURE_FORMULAS",
            }
        else:
            accepted.append(name)
            details[name] = {
                "status": "ACCEPTED",
                "reason": "below_redundancy_threshold",
                "max_abs_corr": top_corr,
                "max_corr_feature": top_name,
                "top5": corrs[:5],
                "formula": FEATURE_FORMULAS.get(name),
                "n_train": int(m.sum()),
            }

    return {
        "fold_used_for_redundancy_gate": fold_id,
        "train_cutoff": cutoff,
        "redundancy_corr_max": REDUNDANCY_CORR_MAX,
        "baseline_cols": list(BASELINE_FEATURE_COLS),
        "accepted": accepted,
        "rejected": rejected,
        "details": details,
        "skipped_families": {
            "vwap": "tick_volume not validated as true volume; VWAP family not computed",
        },
        "existing_feature_overlap_notes": [
            "volatility_12/48 and volatility_ratio_12_48 already capture multi-window RV; rv_6/rv_24 checked for redundancy.",
            "atr_14_pct / candle_range_to_atr / wick ratios already exist; new ATR-normalized rejection and Donchian distance checked against them.",
            "ema spreads / close_to_ema already encode trend; ER/chop/consec_dir intended as efficiency alternatives.",
            "H1 binary trend exists in H13_C path; h1_atr_pct/h1_er_10 add continuous H1 state without incomplete candles.",
        ],
    }
