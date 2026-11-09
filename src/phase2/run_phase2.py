"""Phase 2 orchestrator: audit, chronological OOS training, evaluation.

Does not open the holdout, does not write over Phase 1 files, does not send orders.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evaluation.integrity import assert_holdout_untouched, holdout_status, prepare_research_reads
from evaluation.report import jsonable, save, wrap
from research_kronos_m5 import GUARD
from phase2.constants import (
    FEATURE_ALLOWLIST,
    FEATURE_VERSION,
    LABEL_VERSION,
    OOS_PATH,
    RECIPE_ID,
    REPORTS_DIR,
    SEED,
    SELECTION_RULE,
    TIME_FORMAT,
    UTC_FEATURES_PATH,
)
from phase2.dataset import load_phase2_frame
from phase2.evaluate import evaluate_all
from phase2.feature_audit import run_audit
from phase2.splits import phase2_folds, research_feature_times
from phase2.train_oos import run_walk_forward


def _fold_public(fold: dict) -> dict:
    return {
        "fold_id": fold["fold_id"],
        "eval_start": fold["eval_start"].strftime(TIME_FORMAT),
        "eval_stop": fold["eval_stop"].strftime(TIME_FORMAT),
        "inclusive_stop": fold["inclusive_stop"],
        "train_end": None if pd_isna(fold["train_end"]) else fold["train_end"].strftime(TIME_FORMAT),
        "train_rows": fold["train_rows"],
        "eval_rows": fold["eval_rows"],
        "train_timestamps": fold["train_timestamps"],
        "eval_timestamps": fold["eval_timestamps"],
        "purge_bars": 12,
        "embargo_bars": 0,
    }


def pd_isna(v) -> bool:
    try:
        import pandas as pd
        return bool(pd.isna(v))
    except Exception:
        return v is None


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    boundary = prepare_research_reads(extra_paths=(UTC_FEATURES_PATH,))
    frame, boundary, features = load_phase2_frame(boundary)
    audit = run_audit(frame, boundary)
    save(REPORTS_DIR / "feature_audit.json",
         wrap("phase2_feature_audit", "confirmatory", {"recipe": RECIPE_ID}, audit, SEED))
    if not audit["passed"]:
        print("FEATURE AUDIT FAILED", [c["name"] for c in audit["checks"] if not c["passed"]])
        return 1

    feat_times = research_feature_times(features, boundary["val_end"])
    folds = phase2_folds(frame, feat_times)
    fold_pub = [_fold_public(f) for f in folds]
    save(REPORTS_DIR / "walk_forward_design.json",
         wrap("phase2_walk_forward_design", "confirmatory",
              {"selection_rule": SELECTION_RULE, "feature_version": FEATURE_VERSION},
              {"folds": fold_pub, "n_model_rows": int(len(frame))}, SEED))
    for row in fold_pub:
        print(row["fold_id"], "train_ts", row["train_timestamps"], "eval_ts", row["eval_timestamps"],
              "train_end", row["train_end"])

    preds, registry = run_walk_forward(folds)
    OOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(OOS_PATH, index=False)
    print("wrote", OOS_PATH, "rows", len(preds))

    results = evaluate_all(preds)
    results["registry"] = registry
    results["feature_allowlist"] = list(FEATURE_ALLOWLIST)
    results["feature_version"] = FEATURE_VERSION
    results["label_version"] = LABEL_VERSION
    results["holdout"] = holdout_status()
    save(REPORTS_DIR / "model_results.json",
         wrap("phase2_model_results", "exploratory",
              {"recipe": RECIPE_ID, "selection_rule": SELECTION_RULE}, results, SEED))

    registry_path = REPORTS_DIR / "model_registry.json"
    for item in registry:
        item["status"] = "experimental"
        item["feature_version"] = FEATURE_VERSION
        item["label_version"] = LABEL_VERSION
        item["oos_path"] = str(OOS_PATH)
        item["evaluation_report"] = str(REPORTS_DIR / "model_results.json")
        item["production_ready"] = False
        item["live_ready"] = False
    save(registry_path, wrap("phase2_model_registry", "exploratory",
                             {"recipe": RECIPE_ID}, {"models": registry}, SEED))

    assert_holdout_untouched()
    print("holdout attempts", GUARD["test_open_attempts"])
    e1 = results["economic_e1_rf_reg"]["pooled"]
    print("E1 selected", results["economic_e1_n_selected"],
          "mean_r", e1.get("avg_r"), "pf", e1.get("profit_factor"))
    print("rf clf balanced_acc", results["classification"]["rf"]["pooled"]["balanced_accuracy"])
    print("prior balanced_acc", results["classification"]["prior"]["pooled"]["balanced_accuracy"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
