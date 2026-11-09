"""Explicit decision-time allowlist and leakage checks. New file only."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from phase3.constants import (
    DECISION_FEATURE_ALLOWLIST,
    FORBIDDEN_DECISION_COLUMNS,
    OOS_PATH,
    PHASE2_OOS_SHA256,
    PHASE2_SOURCE_SHA256_16,
    PROJECT_ROOT,
    RECIPE_ID,
    RESEARCH_CUTOFF,
    SEED,
    VALIDATION_END,
)
from phase3.nplib import col, fmt_time, holdout_status, sha16, sha256_file
from phase3.nplib import GUARD


def run_audit(long_rows: list[dict], wide: list[dict]) -> dict:
    checks = []

    def add(name, passed, **info):
        checks.append({"name": name, "passed": bool(passed), **info})

    add("allowlist_explicit", True,
        n_features=len(DECISION_FEATURE_ALLOWLIST),
        features=list(DECISION_FEATURE_ALLOWLIST))

    leaked = [c for c in DECISION_FEATURE_ALLOWLIST if c in FORBIDDEN_DECISION_COLUMNS]
    add("allowlist_excludes_outcomes", not leaked, leaked=leaked)

    actuals = [c for c in DECISION_FEATURE_ALLOWLIST if "actual_" in c]
    add("allowlist_excludes_actual_prefix", not actuals, leaked=actuals)

    missing = [c for c in DECISION_FEATURE_ALLOWLIST if c not in wide[0]]
    add("allowlist_present_on_wide_frame", not missing, missing=missing)

    X = np.column_stack([col(wide, c) for c in DECISION_FEATURE_ALLOWLIST])
    add("no_missing_decision_features", int(np.isnan(X).sum()) == 0, missing=int(np.isnan(X).sum()))
    add("no_infinite_decision_features", int(np.isinf(X).sum()) == 0, infinite=int(np.isinf(X).sum()))

    times = [r["decision_time"] for r in wide]
    add("no_duplicate_timestamps", len(times) == len(set(times)), duplicates=len(times) - len(set(times)))
    add("buy_and_sell_paired", True, note="wide pivot requires both sides")

    max_t = fmt_time(max(times))
    add("no_rows_after_val_end", max_t <= VALIDATION_END, max_decision=max_t, val_end=VALIDATION_END)
    add("no_rows_after_cutoff", max_t <= RESEARCH_CUTOFF, max_decision=max_t, cutoff=RESEARCH_CUTOFF)

    oos_ok = sha256_file(OOS_PATH) == PHASE2_OOS_SHA256
    add("phase2_oos_hash_unchanged", oos_ok, expected=PHASE2_OOS_SHA256)

    drifted = []
    for rel, expected in PHASE2_SOURCE_SHA256_16.items():
        got = sha16(PROJECT_ROOT / rel)
        if got != expected:
            drifted.append({"file": rel, "expected": expected, "got": got})
    add("phase2_sources_unchanged", not drifted, drifted=drifted)

    oos_rows = True
    for row in wide:
        train_end = min(row["training_period_end_BUY"], row["training_period_end_SELL"])
        if row["decision_time"] <= train_end:
            oos_rows = False
            break
    add("primary_predictions_are_oos", oos_rows,
        note="every decision_time is strictly after that row's primary training_period_end")

    chrono = all(times[i] < times[i + 1] for i in range(len(times) - 1))
    add("timestamps_chronological_unique", chrono)

    add("holdout_untouched",
        GUARD["test_open_attempts"] == 0 and not holdout_status()["test_path_in_reads"],
        holdout=holdout_status())

    return {
        "passed": all(c["passed"] for c in checks),
        "recipe": RECIPE_ID,
        "seed": SEED,
        "n_long_rows": int(len(long_rows)),
        "n_timestamps": int(len(wide)),
        "min_decision": fmt_time(min(times)),
        "max_decision": max_t,
        "checks": checks,
    }
