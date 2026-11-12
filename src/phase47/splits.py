"""Chronological date-grouped splits with purge/embargo for H12 overlap."""

from __future__ import annotations

from typing import Any

from phase47.constants import EMBARGO_BARS, ENGINEERING_DATES, MIN_TRAIN_DATES, PURGE_BARS


def walk_forward_folds(dates: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Chronological expanding window:
      train = dates[0:k], eval = dates[k]
    for k in MIN_TRAIN_DATES .. n-1.
    No random splits. No future dates in training.
    """
    dates = list(dates or ENGINEERING_DATES)
    folds = []
    for k in range(MIN_TRAIN_DATES, len(dates)):
        folds.append(
            {
                "fold_id": f"wf_{k}",
                "train_dates": dates[:k],
                "eval_dates": [dates[k]],
                "purge_bars": PURGE_BARS,
                "embargo_bars": EMBARGO_BARS,
                "note": (
                    "Cross-day horizon is 12 M5 bars (~1h) so positions do not span "
                    "engineering date gaps; within-day train/eval never mixed in this fold design."
                ),
            }
        )
    return folds


def partition_rows(
    rows: list[dict[str, Any]],
    train_dates: set[str],
    eval_dates: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = [r for r in rows if str(r["day"]) in train_dates]
    eval_ = [r for r in rows if str(r["day"]) in eval_dates]
    # Integrity: no date overlap
    assert not (train_dates & eval_dates)
    return train, eval_


def assert_no_leakage(train: list[dict[str, Any]], eval_: list[dict[str, Any]]) -> dict[str, Any]:
    td = {str(r["day"]) for r in train}
    ed = {str(r["day"]) for r in eval_}
    overlap = td & ed
    # Within same day should not appear in both
    return {
        "ok": len(overlap) == 0,
        "train_dates": sorted(td),
        "eval_dates": sorted(ed),
        "overlap_dates": sorted(overlap),
        "purge_bars": PURGE_BARS,
        "embargo_bars": EMBARGO_BARS,
    }
