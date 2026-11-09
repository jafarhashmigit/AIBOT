"""Load eligible side outcomes joined to decision-time UTC-corrected features."""

from __future__ import annotations

import pandas as pd

from evaluation.constants import TIME_FORMAT
from evaluation.integrity import prepare_research_reads
from research_kronos_m5 import GUARD, assert_no_test_rows
from phase2.constants import (
    FEATURE_ALLOWLIST,
    OUTCOME_CLASSES,
    OUTCOMES_PATH,
    UTC_FEATURES_PATH,
)


def load_phase2_frame(boundary: dict | None = None) -> pd.DataFrame:
    """Eligible BUY/SELL rows with decision-time features. Outcomes are targets only."""
    if boundary is None:
        boundary = prepare_research_reads(extra_paths=(UTC_FEATURES_PATH,))
    val_end = boundary["val_end"]
    cutoff = boundary["cutoff"]

    outcomes = pd.read_csv(OUTCOMES_PATH)
    outcomes["decision_time"] = pd.to_datetime(outcomes["decision_time"], format=TIME_FORMAT, errors="coerce")
    for col in ("entry_time", "exit_time"):
        outcomes[col] = pd.to_datetime(outcomes[col], format=TIME_FORMAT, errors="coerce")
    outcomes = outcomes[outcomes["decision_time"] <= val_end].reset_index(drop=True)
    assert_no_test_rows(outcomes, column="decision_time")
    if outcomes["decision_time"].max() > cutoff:
        raise RuntimeError("side outcomes extend past the research cutoff")

    features = pd.read_csv(UTC_FEATURES_PATH)
    features["time"] = pd.to_datetime(features["time"], format=TIME_FORMAT)
    features = features[features["time"] <= cutoff].reset_index(drop=True)
    assert_no_test_rows(features)
    missing = [c for c in FEATURE_ALLOWLIST if c not in features.columns]
    if missing:
        raise RuntimeError(f"UTC feature file missing allowlist columns: {missing}")

    feat = features[["time", *FEATURE_ALLOWLIST]].rename(columns={"time": "decision_time"})
    eligible = outcomes[outcomes["eligible"]].copy()
    merged = eligible.merge(feat, on="decision_time", how="inner", validate="many_to_one")
    if merged["exit_reason"].isna().any() or merged["net_r"].isna().any():
        raise RuntimeError("eligible joined rows have missing targets")
    unknown = sorted(set(merged["exit_reason"].unique()) - set(OUTCOME_CLASSES))
    if unknown:
        raise RuntimeError(f"unexpected exit_reason values: {unknown}")
    if not merged["decision_time"].is_monotonic_increasing:
        merged = merged.sort_values(["decision_time", "side"]).reset_index(drop=True)
    GUARD["csv_reads"]
    return merged, boundary, features
