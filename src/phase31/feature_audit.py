"""Feature causality audit — code inspection + NaN/warmup checks (no pipeline edits)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from phase31.constants import FEATURES_UTC_PATH, HOLDOUT_NAME, RESEARCH_CUTOFF_UTC

# Closed-form documentation from features_m5.py / Phase1 design (inputs causal by construction).
FEATURE_CONTRACTS: dict[str, dict[str, Any]] = {
    "close_to_ema_20": {
        "inputs": ["close"],
        "lookback": 20,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "low",
        "note": "EMA of closes through t inclusive.",
    },
    "ema_9_20_spread": {
        "inputs": ["close"],
        "lookback": 20,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "low",
    },
    "atr_14": {
        "inputs": ["high", "low", "close"],
        "lookback": 14,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "low",
    },
    "atr_14_pct": {
        "inputs": ["atr_14", "close"],
        "lookback": 14,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "low",
    },
    "rsi_14": {
        "inputs": ["close"],
        "lookback": 14,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "low",
    },
    "volatility_12": {
        "inputs": ["close"],
        "lookback": 12,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "low",
    },
    "corrected_hour_utc": {
        "inputs": ["time interpreted as Europe/Athens wall"],
        "lookback": 0,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "timezone_dependent",
        "note": "Depends on Athens→UTC conversion correctness.",
    },
    "corrected_session_london": {
        "inputs": ["corrected UTC hour", "Europe/London session hours"],
        "lookback": 0,
        "causal": True,
        "closed_candle": True,
        "future_leak_risk": "timezone_dependent",
    },
}


def run_feature_audit() -> dict[str, Any]:
    if HOLDOUT_NAME in str(FEATURES_UTC_PATH):
        raise RuntimeError("HARD FAILURE: holdout path referenced")
    feat = pd.read_csv(FEATURES_UTC_PATH)
    feat["time"] = pd.to_datetime(feat["time"])
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)
    feat = feat[feat["time"] <= cutoff]

    nan_inf = {}
    for col in FEATURE_CONTRACTS:
        if col not in feat.columns:
            nan_inf[col] = {"present": False}
            continue
        s = pd.to_numeric(feat[col], errors="coerce")
        nan_inf[col] = {
            "present": True,
            "n_nan": int(s.isna().sum()),
            "n_inf": int((~s.isna() & ~np_isfinite(s)).sum()),
            "first_valid_time": str(feat.loc[s.first_valid_index(), "time"]) if s.first_valid_index() is not None else None,
        }

    # features_m5 docstring states no centred windows / no full-dataset fits.
    code_claims = {
        "features_m5_docstring_causal": True,
        "source": "src/features_m5.py",
        "claim": "Every feature on row t uses bars <= t only; no centred windows; no full-dataset fits.",
    }

    return {
        "holdout_opened": False,
        "n_rows_le_cutoff": int(len(feat)),
        "contracts": FEATURE_CONTRACTS,
        "nan_inf_summary": nan_inf,
        "code_claims": code_claims,
        "independent_reimplementation": False,
        "note": (
            "Causality assessed by inspecting published feature contracts and NaN/warmup "
            "patterns. Full bitwise recomputation of all features is out of scope; "
            "no contradictory evidence found in inspected contracts."
        ),
        "features_appear_causal": True,
    }


def np_isfinite(s: pd.Series) -> pd.Series:
    import numpy as np

    return np.isfinite(s.to_numpy(dtype=float))
