"""Chronological walk-forward splits with purge and optional embargo.

Training rows are never shuffled. The default purge matches the existing
12-bar label window (label_m5.PURGE_BARS). An extra embargo (bars after the
purge) is available for future experiments and defaults to 0 so historical
reproductions stay bit-compatible with research_m5_label_horizon.purged_split.
"""

from __future__ import annotations

import pandas as pd

from evaluation.constants import EXPECTED_WF_WINDOWS, TIME_FORMAT, WF_BOUNDARY_FRACTIONS
from features_m5 import BAR_MINUTES
from label_m5 import HORIZON_BARS, PURGE_BARS
from research_m5_label_horizon import purged_split as existing_purged_split

BAR = pd.Timedelta(minutes=BAR_MINUTES)


def walk_forward_windows(times: pd.Series, fractions=WF_BOUNDARY_FRACTIONS,
                         expected=EXPECTED_WF_WINDOWS) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Three consecutive windows starting at the given fractions of `times`.

    `times` must already be the research-period feature timestamps, sorted.
    WF3 includes its end stamp, matching every earlier M5 experiment.
    """
    if not times.is_monotonic_increasing or not times.is_unique:
        raise ValueError("timestamps must be unique and chronological")
    starts = [times.iloc[int(len(times) * q)] for q in fractions]
    windows = [(starts[0], starts[1]), (starts[1], starts[2]), (starts[2], times.iloc[-1])]
    as_str = [(a.strftime(TIME_FORMAT), b.strftime(TIME_FORMAT)) for a, b in windows]
    if expected is not None and as_str != list(expected):
        raise AssertionError(f"walk-forward windows changed: {as_str} != {expected}")
    return windows


def purge_before_boundary(train: pd.DataFrame, boundary: pd.Timestamp,
                          horizon_bars: int = HORIZON_BARS,
                          embargo_bars: int = 0) -> pd.DataFrame:
    """Drop rows whose label window (and optional embargo) reaches `boundary`."""
    label_end = train["time"] + pd.Timedelta(minutes=BAR_MINUTES * (horizon_bars + embargo_bars))
    return train[label_end < boundary]


def purged_expanding_split(labeled: pd.DataFrame, val_start, val_stop, *,
                           last_window: bool,
                           horizon_bars: int = HORIZON_BARS,
                           embargo_bars: int = 0):
    """Expanding train / blocked validation with purge.

    embargo_bars=0 reproduces research_m5_label_horizon.purged_split.
    embargo_bars>0 additionally drops training rows whose embargo after the
    label window still overlaps the validation start.
    """
    if embargo_bars == 0:
        return existing_purged_split(labeled, horizon_bars, val_start, val_stop,
                                     inclusive_stop=last_window)
    window = (horizon_bars + embargo_bars) * BAR
    train = labeled[(labeled["time"] < val_start) & (labeled["time"] + window < val_start)]
    in_val = labeled["time"] <= val_stop if last_window else labeled["time"] < val_stop
    val = labeled[(labeled["time"] >= val_start) & in_val]
    if len(train) and len(val):
        assert train["time"].max() + window < val["time"].min(), "label/embargo window leaks into validation"
    return train, val


def assert_chronological(df: pd.DataFrame, column: str = "time") -> None:
    if not df[column].is_monotonic_increasing or not df[column].is_unique:
        raise AssertionError(f"{column} is not strictly chronological")
