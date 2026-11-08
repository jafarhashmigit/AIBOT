"""Phase 1 orchestrator: reproduction, new datasets, G2, MT5 probe.

Does not retrain a production model, does not overwrite existing research
outputs, does not open the holdout, and does not send orders.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evaluation.constants import DEFAULT_SEED, RESEARCH_CUTOFF
from evaluation.gates import evaluate_g2
from evaluation.integrity import (
    assert_holdout_untouched,
    holdout_status,
    prepare_research_reads,
    reports_dir,
    snapshot_existing,
    snapshots_equal,
)
from evaluation.report import save, wrap
from evaluation.reproduce import load_labeled_research, reproduce_conditional_edge, reproduce_rf_validation
from research_kronos_m5 import GUARD
from research_m5_label_horizon import load_research_data

from build_m5_side_outcomes import run as build_side_outcomes
from build_m5_utc_corrected_features import run as build_utc_features
from probe_m5_history_depth import run as probe_m5_history


def _drop_frames(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in {"wf_trades", "groups"}}


def main() -> int:
    boundary = prepare_research_reads()
    cutoff_str = boundary["cutoff_str"]
    before = snapshot_existing(cutoff_str)
    blocked = []
    out = {
        "boundary": {
            "val_start": boundary["val_start_str"],
            "val_end": boundary["val_end_str"],
            "cutoff": cutoff_str,
        },
        "holdout_start": holdout_status(),
    }

    # Task 3a — RF validation reproduction
    rf = reproduce_rf_validation()
    out["rf_validation"] = rf
    save(reports_dir() / "rf_validation_reproduction.json",
         wrap("rf_validation_reproduction", "reproduction",
              {"model": "rf_m5_baseline.pkl", "period": "validation"}, rf, DEFAULT_SEED))
    if not rf["exact_match_to_saved_csv"] or not rf["rounded_match_to_published_report"]:
        blocked.append("rf_validation_mismatch")
        print("RF validation reproduction DISCREPANCY — stopping CE and G2")

    # Task 4 — per-side outcomes
    out["side_outcomes"] = build_side_outcomes(boundary)

    # Task 5 — UTC-corrected features
    try:
        out["utc_features"] = build_utc_features(boundary)
    except Exception as exc:
        blocked.append("utc_features")
        out["utc_features"] = {"status": "blocked", "error": str(exc)}
        print("UTC correction blocked:", exc)

    # Task 3b — conditional-edge reproduction (in memory)
    ce = None
    if "rf_validation_mismatch" in blocked:
        out["conditional_edge"] = {"status": "skipped", "reason": "RF validation did not reproduce"}
    else:
        raw, features, _ = load_research_data(boundary["val_end"], boundary["cutoff"])
        labeled = load_labeled_research(boundary["val_end"], boundary["cutoff"])
        ce = reproduce_conditional_edge(raw, features, labeled)
        report_ce = _drop_frames(ce)
        out["conditional_edge"] = report_ce
        save(reports_dir() / "conditional_edge_reproduction.json",
             wrap("conditional_edge_reproduction", "reproduction",
                  {"windows": "WF1-WF3 expanding, 12-bar purge, frozen RF_PARAMS"},
                  report_ce, DEFAULT_SEED))
        if ce["n_mismatches_vs_saved_csv"] or not ce["conclusion_matches_saved"]:
            blocked.append("conditional_edge_mismatch")
            print("Conditional-edge DISCREPANCY — stopping G2")

    # Task 8 — G2 on the existing walk-forward RF baseline
    if ce is None or "conditional_edge_mismatch" in blocked:
        out["g2"] = {"status": "skipped", "reason": "reproduction discrepancy; G2 not run"}
        blocked.append("g2_not_run")
    else:
        pool = None
        side_path = SRC / "data" / "m5_side_outcomes.csv"
        if side_path.exists():
            import pandas as pd
            pool = pd.read_csv(side_path)
            pool = pool[pool["eligible"]].copy()
        g2 = evaluate_g2(ce["wf_trades"], outcome_pool=pool, family_size=1,
                         run_permutation_a=False,
                         permutation_a_reason=(
                             "Phase 1 skips 200 RF retrains because G2 mean-R / CI are "
                             "expected to fail on this baseline; skipping blocks a pass."
                         ))
        out["g2"] = {k: v for k, v in g2.items() if k != "criteria"}
        out["g2"]["criteria"] = g2["criteria"]
        save(reports_dir() / "rf_baseline_g2.json",
             wrap("rf_baseline_g2", "reproduction",
                  {"gate": "G2", "candidate": "rf_m5_walk_forward_frozen_params"},
                  g2, DEFAULT_SEED))
        if g2["passed"] or not g2.get("economic_failed"):
            blocked.append("g2_unexpected_pass")
            print("G2 UNEXPECTED PASS — stopping", g2.get("hard_fail"), g2.get("economic_failed"))
        else:
            print("G2 passed=False (expected). economic_failed=", g2.get("economic_failed"),
                  "incomplete=", g2.get("incomplete"))

    # Task 7 — MT5 depth probe (no project datasets written)
    try:
        out["mt5_probe"] = probe_m5_history()
    except Exception as exc:
        out["mt5_probe"] = {"status": "blocked", "error": str(exc)}
        blocked.append("mt5_probe")
        print("MT5 probe blocked:", exc)

    after = snapshot_existing(cutoff_str)
    unchanged, diffs = snapshots_equal(before, after)
    new_keys = sorted(set(after) - set(before))
    out["integrity"] = {
        "existing_keys_unchanged": unchanged,
        "changed_existing_keys": diffs,
        "new_keys": new_keys,
        "holdout": holdout_status(),
        "test_open_attempts": GUARD["test_open_attempts"],
    }
    if not unchanged:
        blocked.append("existing_files_changed")
    try:
        assert_holdout_untouched()
    except RuntimeError as exc:
        blocked.append("holdout_touched")
        out["integrity"]["holdout_error"] = str(exc)

    out["blocked"] = blocked
    out["phase1_tasks_that_require_g2"] = "complete" if "g2_not_run" not in blocked and "g2_unexpected_pass" not in blocked else "incomplete"
    save(reports_dir() / "phase1_summary.json",
         wrap("phase1_summary", "reproduction",
              {"research_cutoff": RESEARCH_CUTOFF}, out, DEFAULT_SEED))
    print("Phase 1 orchestrator blocked:", blocked or "none")
    print("holdout attempts", GUARD["test_open_attempts"])
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
