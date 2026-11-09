"""Nested chronological splits for the decision layer."""

from __future__ import annotations

from datetime import timedelta

from phase3.constants import BAR_MINUTES, HORIZON_BARS, NESTED_FOLDS
from phase3.nplib import fmt_time, parse_time


def nested_folds(wide: list[dict]) -> list[dict]:
    window = timedelta(minutes=BAR_MINUTES * HORIZON_BARS)
    folds = []
    for spec in NESTED_FOLDS:
        outer_start = parse_time(spec["outer_start"])
        outer_stop = parse_time(spec["outer_stop"])
        inner_folds = set(spec["inner_phase2_folds"])
        outer_fold = spec["outer_phase2_fold"]
        inner, outer = [], []
        for row in wide:
            t = row["decision_time"]
            if row["fold_id"] in inner_folds and t + window < outer_start:
                inner.append(row)
            in_outer_fold = row["fold_id"] == outer_fold and t >= outer_start
            if spec["inclusive_stop"]:
                in_outer_fold = in_outer_fold and t <= outer_stop
            else:
                in_outer_fold = in_outer_fold and t < outer_stop
            if in_outer_fold:
                outer.append(row)
        if not inner or not outer:
            raise RuntimeError(f"{spec['nested_id']}: inner or outer is empty")
        if inner[-1]["decision_time"] + window >= outer[0]["decision_time"]:
            raise RuntimeError(f"{spec['nested_id']}: purge failed")
        inner_times = {r["decision_time"] for r in inner}
        outer_times = {r["decision_time"] for r in outer}
        if inner_times & outer_times:
            raise RuntimeError(f"{spec['nested_id']}: timestamp in inner and outer")
        folds.append({
            "nested_id": spec["nested_id"],
            "inner_phase2_folds": list(spec["inner_phase2_folds"]),
            "outer_phase2_fold": outer_fold,
            "outer_start": outer_start,
            "outer_stop": outer_stop,
            "inclusive_stop": spec["inclusive_stop"],
            "inner": inner,
            "outer": outer,
            "inner_timestamps": len(inner),
            "outer_timestamps": len(outer),
            "inner_end": inner[-1]["decision_time"],
            "outer_first": outer[0]["decision_time"],
            "outer_last": outer[-1]["decision_time"],
            "purge_bars": HORIZON_BARS,
            "embargo_bars": 0,
        })
    return folds


def fold_public(fold: dict) -> dict:
    return {
        "nested_id": fold["nested_id"],
        "inner_phase2_folds": fold["inner_phase2_folds"],
        "outer_phase2_fold": fold["outer_phase2_fold"],
        "outer_start": fmt_time(fold["outer_start"]),
        "outer_stop": fmt_time(fold["outer_stop"]),
        "inclusive_stop": fold["inclusive_stop"],
        "inner_timestamps": fold["inner_timestamps"],
        "outer_timestamps": fold["outer_timestamps"],
        "inner_end": fmt_time(fold["inner_end"]),
        "outer_first": fmt_time(fold["outer_first"]),
        "outer_last": fmt_time(fold["outer_last"]),
        "purge_bars": fold["purge_bars"],
        "embargo_bars": fold["embargo_bars"],
        "rationale": (
            "Expanding inner calibration on earlier Phase 2 OOS predictions; "
            "outer fold used once for decision evaluation. 12-bar purge prevents "
            "inner label windows from overlapping the outer period."
        ),
    }
