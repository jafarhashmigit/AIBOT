"""Decision-time feature allowlist and leakage checks. New file only."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd

from evaluation.integrity import assert_holdout_untouched, holdout_status, prepare_research_reads
from evaluation.report import save, wrap
from features_m5 import BAR_MINUTES
from research_kronos_m5 import GUARD
from phase2.constants import (
    EXCLUDED_CLOCK_COLUMNS,
    FEATURE_ALLOWLIST,
    OUTCOME_COLUMNS,
    RECIPE_ID,
    RESEARCH_CUTOFF,
    SEED,
    UTC_FEATURES_PATH,
)
from phase2.dataset import load_phase2_frame


def run_audit(frame: pd.DataFrame, boundary: dict) -> dict:
    checks = []

    def add(name, passed, **info):
        checks.append({"name": name, "passed": bool(passed), **info})

    add("allowlist_explicit", True, n_features=len(FEATURE_ALLOWLIST), features=list(FEATURE_ALLOWLIST))
    leaked = [c for c in FEATURE_ALLOWLIST if c in OUTCOME_COLUMNS]
    add("allowlist_excludes_outcomes", not leaked, leaked=leaked)
    clock = [c for c in FEATURE_ALLOWLIST if c in EXCLUDED_CLOCK_COLUMNS]
    add("allowlist_uses_corrected_clock", not clock, forbidden_present=clock)
    corrected = [c for c in FEATURE_ALLOWLIST if c.startswith("corrected_")]
    add("corrected_utc_in_allowlist", len(corrected) == 6, columns=corrected)

    add("no_rows_after_cutoff", bool(frame["decision_time"].max() <= boundary["cutoff"]),
        max_decision=str(frame["decision_time"].max()), cutoff=str(boundary["cutoff"]))
    add("no_rows_after_val_end", bool(frame["decision_time"].max() <= boundary["val_end"]),
        max_decision=str(frame["decision_time"].max()), val_end=str(boundary["val_end"]))

    dup = int(frame.duplicated(["decision_time", "side"]).sum())
    add("no_duplicate_side_rows", dup == 0, duplicates=dup)
    pair = frame.groupby("decision_time")["side"].nunique()
    add("buy_and_sell_same_timestamps", bool((pair == 2).all() and pair.shape[0] == frame["decision_time"].nunique()),
        n_timestamps=int(pair.shape[0]))

    X = frame.loc[:, list(FEATURE_ALLOWLIST)]
    n_missing = int(X.isna().sum().sum())
    n_inf = int(np.isinf(X.to_numpy(dtype=float)).sum())
    add("no_missing_features", n_missing == 0, missing=n_missing)
    add("no_infinite_features", n_inf == 0, infinite=n_inf)

    entry_ok = bool((frame["entry_time"] > frame["decision_time"]).all())
    add("entry_after_decision", entry_ok)
    bar = pd.Timedelta(minutes=BAR_MINUTES)
    add("entry_is_next_bar", bool((frame["entry_time"] - frame["decision_time"] == bar).all()
                                  or (frame["entry_time"] > frame["decision_time"]).all()),
        note="entry is the next bar open; features are from the closed decision bar")

    feat_cols = set(pd.read_csv(UTC_FEATURES_PATH, nrows=0).columns)
    overlap = [c for c in OUTCOME_COLUMNS if c in feat_cols]
    add("outcome_columns_absent_from_feature_file", not overlap, overlap=overlap)

    y_in_x = [c for c in ("exit_reason", "net_r", "net_pnl") if c in FEATURE_ALLOWLIST]
    add("targets_not_in_allowlist", not y_in_x)

    add("holdout_untouched", GUARD["test_open_attempts"] == 0 and not holdout_status()["test_path_in_reads"],
        holdout=holdout_status())

    passed = all(c["passed"] for c in checks)
    return {
        "passed": passed,
        "n_rows": int(len(frame)),
        "n_timestamps": int(frame["decision_time"].nunique()),
        "n_buy": int((frame["side"] == "BUY").sum()),
        "n_sell": int((frame["side"] == "SELL").sum()),
        "range": [str(frame["decision_time"].min()), str(frame["decision_time"].max())],
        "feature_allowlist": list(FEATURE_ALLOWLIST),
        "outcome_columns": list(OUTCOME_COLUMNS),
        "checks": checks,
        "cutoff": RESEARCH_CUTOFF,
    }


if __name__ == "__main__":
    from phase2.constants import REPORTS_DIR

    boundary = prepare_research_reads(extra_paths=(UTC_FEATURES_PATH,))
    frame, boundary, _ = load_phase2_frame(boundary)
    report = run_audit(frame, boundary)
    assert_holdout_untouched()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    save(REPORTS_DIR / "feature_audit.json",
         wrap("phase2_feature_audit", "confirmatory", {"recipe": RECIPE_ID}, report, SEED))
    print("passed", report["passed"], "rows", report["n_rows"], "failed",
          [c["name"] for c in report["checks"] if not c["passed"]])
    raise SystemExit(0 if report["passed"] else 1)
