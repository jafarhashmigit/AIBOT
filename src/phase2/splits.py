"""Chronological expanding-window splits that keep both sides of a timestamp together."""

from __future__ import annotations

import pandas as pd

from evaluation.constants import EXPECTED_WF_WINDOWS, TIME_FORMAT
from evaluation.splits import walk_forward_windows
from features_m5 import BAR_MINUTES
from label_m5 import HORIZON_BARS
from phase2.constants import SIDES


def unique_decision_times(frame: pd.DataFrame) -> pd.Series:
    times = pd.Series(frame["decision_time"].unique()).sort_values().reset_index(drop=True)
    if not times.is_monotonic_increasing or not times.is_unique:
        raise AssertionError("decision timestamps are not strictly chronological")
    return times


def fold_masks(frame: pd.DataFrame, windows, horizon_bars: int = HORIZON_BARS) -> list[dict]:
    """Expanding train / blocked eval. Purge = label window must end before eval start."""
    window = pd.Timedelta(minutes=BAR_MINUTES * horizon_bars)
    folds = []
    for i, (start, stop) in enumerate(windows, 1):
        last = i == len(windows)
        in_eval = (frame["decision_time"] >= start) & (
            (frame["decision_time"] <= stop) if last else (frame["decision_time"] < stop)
        )
        trainable = frame["decision_time"] + window < start
        train, eval_ = frame[trainable], frame[in_eval]
        if len(train) and len(eval_):
            if train["decision_time"].max() + window >= eval_["decision_time"].min():
                raise AssertionError("purge failed: training label window reaches evaluation")
        train_times, eval_times = set(train["decision_time"]), set(eval_["decision_time"])
        if train_times & eval_times:
            raise AssertionError("a decision timestamp is in both train and eval")
        for side in SIDES:
            n_tr = int((train["side"] == side).sum())
            n_ev = int((eval_["side"] == side).sum())
            if n_tr != train["decision_time"].nunique() or n_ev != eval_["decision_time"].nunique():
                raise AssertionError(f"{side} is not paired 1:1 with decision timestamps in fold WF{i}")
        folds.append({
            "fold_id": f"WF{i}",
            "eval_start": start,
            "eval_stop": stop,
            "inclusive_stop": last,
            "train": train.reset_index(drop=True),
            "eval": eval_.reset_index(drop=True),
            "train_end": train["decision_time"].max() if len(train) else pd.NaT,
            "train_rows": int(len(train)),
            "eval_rows": int(len(eval_)),
            "train_timestamps": int(train["decision_time"].nunique()),
            "eval_timestamps": int(eval_["decision_time"].nunique()),
        })
    return folds


def research_feature_times(features: pd.DataFrame, val_end) -> pd.Series:
    """Feature timestamps through validation end — the Phase 1 window index."""
    times = features.loc[features["time"] <= val_end, "time"]
    if isinstance(times, pd.DataFrame):
        times = times.iloc[:, 0]
    times = times.sort_values().reset_index(drop=True)
    return times


def phase2_folds(frame: pd.DataFrame, feature_times: pd.Series) -> list[dict]:
    windows = walk_forward_windows(feature_times)
    as_str = [(a.strftime(TIME_FORMAT), b.strftime(TIME_FORMAT)) for a, b in windows]
    if as_str != list(EXPECTED_WF_WINDOWS):
        raise AssertionError(f"walk-forward windows drifted: {as_str}")
    return fold_masks(frame, windows)
