"""Holdout guards, cutoff-capped reads, and file-integrity snapshots.

Wraps the existing research_kronos_m5 / research_rf_m5_conditional_edge helpers.
Does not hash or open xauusd_m5_test.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from evaluation.constants import DATA_DIR, PROJECT_ROOT, REPORTS_DIR, RESEARCH_CUTOFF, SRC_DIR, TIME_FORMAT
from label_m5 import FEATURES_PATH, RAW_PATH
from research_kronos_m5 import GUARD, TEST_PATH, assert_no_test_rows, install_guards, rows_through
from research_m5_label_horizon import VALIDATION_PATH, research_boundary
from research_rf_m5_conditional_edge import snapshot

LABELED_PATH = DATA_DIR / "xauusd_m5_labeled.csv"
SKIP_ALWAYS = {TEST_PATH.resolve()}


def rows_at_most(path: Path, cutoff: str) -> int:
    """Count data rows with timestamp <= cutoff. Stops before any later stamp.

    Unlike rows_through(), this does not require an exact cutoff stamp (the
    labeled file has no row at 18:50).
    """
    with open(path, "r", encoding="utf-8") as fh:
        header = fh.readline()
        if not header.startswith("time,"):
            raise RuntimeError(f"{path.name}: unexpected header")
        n = 0
        for line in fh:
            stamp = line[:19]
            if stamp > cutoff:
                return n
            n += 1
    return n


def prepare_research_reads(extra_paths: tuple[Path, ...] = ()) -> dict:
    """Install holdout guards and cap raw/feature/labeled CSV reads at the cutoff.

    Returns boundary timestamps. The test CSV is never opened.
    """
    install_guards()
    val_start, val_end, cutoff = research_boundary()
    cutoff_str = cutoff.strftime(TIME_FORMAT)
    if cutoff_str != RESEARCH_CUTOFF:
        raise RuntimeError(f"research cutoff drifted: {cutoff_str} != {RESEARCH_CUTOFF}")
    GUARD["cutoff"] = cutoff_str
    val_end_str = val_end.strftime(TIME_FORMAT)
    # Raw/features may include the 12-bar purge gap (timestamps <= cutoff).
    # Labels after val_end were computed from bars after the cutoff — do not read them.
    caps = {
        RAW_PATH.resolve(): cutoff_str,
        FEATURES_PATH.resolve(): cutoff_str,
        LABELED_PATH.resolve(): val_end_str,
    }
    for path in extra_paths:
        caps[Path(path).resolve()] = cutoff_str
    for resolved, cap in caps.items():
        if resolved == TEST_PATH.resolve() or resolved.name == "xauusd_m5_test.csv":
            raise RuntimeError("refusing to register the test CSV as a readable path")
        GUARD["safe_nrows"][resolved] = rows_at_most(resolved, cap)
    return {
        "val_start": val_start,
        "val_end": val_end,
        "cutoff": cutoff,
        "cutoff_str": cutoff_str,
        "val_start_str": val_start.strftime(TIME_FORMAT),
        "val_end_str": val_end.strftime(TIME_FORMAT),
    }


def snapshot_existing(cutoff_str: str, extra_skip: set | None = None) -> dict:
    skip = {p.resolve() for p in extra_skip or []}
    skip.add(TEST_PATH.resolve())
    return snapshot(skip, cutoff_str)


def snapshots_equal(before: dict, after: dict) -> tuple[bool, list[str]]:
    """Compare only keys that existed before. New files are reported separately."""
    diffs = [key for key in sorted(before) if before[key] != after.get(key)]
    return not diffs, diffs


def holdout_status() -> dict:
    return {
        "test_open_attempts": GUARD["test_open_attempts"],
        "cutoff": GUARD["cutoff"],
        "csv_reads": sorted({p.name for p in GUARD["csv_reads"]}),
        "test_path_in_reads": TEST_PATH.resolve() in GUARD["csv_reads"],
    }


def assert_holdout_untouched() -> None:
    if GUARD["test_open_attempts"] != 0 or TEST_PATH.resolve() in GUARD["csv_reads"]:
        raise RuntimeError("TEST DATASET ACCESS DETECTED")
    if GUARD["cutoff"] is None:
        raise RuntimeError("guards were not installed")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR
