"""Phase 32 preflight."""

from __future__ import annotations

from typing import Any

from phase32.constants import (
    EXPECTED_FEATURE_ROWS,
    EXPECTED_LABELED_ROWS,
    EXPECTED_RAW_ROWS,
    EXPECTED_UTC_FEATURE_ROWS,
    FEATURES_PATH,
    FEATURES_UTC_PATH,
    LABELED_PATH,
    PHASE31_FINAL,
    RAW_M5_PATH,
    RECIPE_ID,
    RESEARCH_CUTOFF_UTC,
)
from phase32.integrity import safety_snapshot
import pandas as pd


def run_preflight() -> dict[str, Any]:
    safety = safety_snapshot()
    counts = {
        "raw": int(len(pd.read_csv(RAW_M5_PATH, usecols=["time"]))),
        "features": int(len(pd.read_csv(FEATURES_PATH, usecols=["time"]))),
        "features_utc": int(len(pd.read_csv(FEATURES_UTC_PATH, usecols=["time"]))),
        "labeled": int(len(pd.read_csv(LABELED_PATH, usecols=["time"]))),
    }
    return {
        "recipe": RECIPE_ID,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "safety": safety,
        "counts": counts,
        "expected": {
            "raw": EXPECTED_RAW_ROWS,
            "features": EXPECTED_FEATURE_ROWS,
            "features_utc": EXPECTED_UTC_FEATURE_ROWS,
            "labeled": EXPECTED_LABELED_ROWS,
        },
        "count_matches_expected": {
            "raw": counts["raw"] == EXPECTED_RAW_ROWS,
            "features": counts["features"] == EXPECTED_FEATURE_ROWS,
            "features_utc": counts["features_utc"] == EXPECTED_UTC_FEATURE_ROWS,
            "labeled": counts["labeled"] == EXPECTED_LABELED_ROWS,
        },
        "phase31_final_present": PHASE31_FINAL.exists(),
        "ok": bool(safety["protected_artifacts_intact"] and safety["cutoff_ok"]),
    }
