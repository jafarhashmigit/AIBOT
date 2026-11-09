"""Write Phase 2 model-registry JSON from existing artifacts. Does not retrain.

Stdlib only so it does not depend on pandas at write time.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
MODELS_DIR = SRC / "models" / "phase2"
REPORTS_DIR = ROOT / "reports" / "phase2"
OOS_PATH = SRC / "data" / "phase2_oos_predictions.csv"

FEATURE_ALLOWLIST = [
    "close_to_ema_9", "close_to_ema_50", "ema_9_20_spread", "ema_20_50_spread",
    "rsi_14", "bb_percent_b", "bb_width", "atr_14_pct", "volatility_12",
    "volatility_48", "volatility_ratio_12_48", "candle_body_abs_to_range",
    "upper_wick_to_range", "lower_wick_to_range", "candle_range_to_atr",
    "log_return_1", "return_3", "return_6", "return_12", "roc_20",
    "log_tick_volume", "tick_volume_change", "tick_volume_ratio_20",
    "minutes_since_prev_bar", "corrected_hour_utc", "corrected_weekday_utc",
    "corrected_session_asia", "corrected_session_london",
    "corrected_session_new_york", "corrected_session_london_ny_overlap",
]
FEATURE_VERSION = "m5_utc_corrected_allowlist_v1"
LABEL_VERSION = "m5_side_outcomes_exit_reason_net_r_v1"
RECIPE_ID = "phase2_primary_outcome_v1"
SEED = 42
LOGREG_PARAMS = {"max_iter": 1000, "C": 1.0, "class_weight": "balanced", "solver": "lbfgs", "random_state": SEED}
RF_CLF_PARAMS = {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 50, "max_features": "sqrt",
                 "max_samples": 0.5, "bootstrap": True, "class_weight": "balanced", "random_state": SEED, "n_jobs": -1}
RIDGE_PARAMS = {"alpha": 1.0}
RF_REG_PARAMS = {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 50, "max_features": "sqrt",
                 "max_samples": 0.5, "bootstrap": True, "random_state": SEED, "n_jobs": -1}
FOLDS = {
    "WF1": {"eval": ("2026-06-19 03:05:00", "2026-07-23 11:25:00"), "train_end": "2026-06-19 02:00:00"},
    "WF2": {"eval": ("2026-07-23 11:25:00", "2026-08-26 13:55:00"), "train_end": "2026-07-23 10:20:00"},
    "WF3": {"eval": ("2026-08-26 13:55:00", "2026-09-29 17:50:00"), "train_end": "2026-08-26 12:50:00"},
}


def main() -> None:
    feat_hash = hashlib.sha256("\n".join(FEATURE_ALLOWLIST).encode()).hexdigest()
    models = []
    missing = []
    for fold, info in FOLDS.items():
        for side in ("BUY", "SELL"):
            scaler = str(MODELS_DIR / f"scaler_{side}_{fold}.pkl")
            specs = [
                (f"prior_{side}_{fold}", "class_prior", {"empirical_train_frequencies": True}, None, None, "exit_reason"),
                (f"logreg_{side}_{fold}", "logistic_regression", LOGREG_PARAMS,
                 str(MODELS_DIR / f"logreg_{side}_{fold}.pkl"), scaler, "exit_reason"),
                (f"rfclf_{side}_{fold}", "random_forest_classifier", RF_CLF_PARAMS,
                 str(MODELS_DIR / f"rfclf_{side}_{fold}.pkl"), None, "exit_reason"),
                (f"const_{side}_{fold}", "constant_mean_r", {"mean_of_training_net_r": True}, None, None, "net_r"),
                (f"ridge_{side}_{fold}", "ridge_regression", RIDGE_PARAMS,
                 str(MODELS_DIR / f"ridge_{side}_{fold}.pkl"), scaler, "net_r"),
                (f"rfreg_{side}_{fold}", "random_forest_regressor", RF_REG_PARAMS,
                 str(MODELS_DIR / f"rfreg_{side}_{fold}.pkl"), None, "net_r"),
            ]
            for model_id, model_type, params, artifact, scaler_path, target in specs:
                if artifact and not Path(artifact).exists():
                    missing.append(artifact)
                models.append({
                    "model_id": model_id,
                    "model_type": model_type,
                    "model_version": RECIPE_ID,
                    "role": "primary",
                    "side": side,
                    "fold_id": fold,
                    "training_date": "2026-11-08",
                    "training_period_end": info["train_end"],
                    "evaluation_window": {"start": info["eval"][0], "stop": info["eval"][1]},
                    "feature_list": FEATURE_ALLOWLIST,
                    "feature_version": FEATURE_VERSION,
                    "feature_list_sha256": feat_hash,
                    "target_definition": target,
                    "label_version": LABEL_VERSION,
                    "fold_definitions": FOLDS,
                    "parameters": params,
                    "random_seed": SEED,
                    "python": "3.12.10",
                    "dependencies": {"scikit-learn": "1.9.1", "pandas": "3.1.1", "numpy": "2.5.4"},
                    "artifact_path": artifact,
                    "scaler_path": scaler_path,
                    "evaluation_report_path": str(REPORTS_DIR / "model_results.json"),
                    "oos_prediction_path": str(OOS_PATH),
                    "known_limitations": [
                        "Exploratory only. Weak R correlation. E1 mean R negative in every fold.",
                        "Phase 1 permutation A remains not_run.",
                    ],
                    "status": "experimental",
                    "approval_status": "registered",
                    "production_ready": False,
                    "live_ready": False,
                })
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "report": "phase2_model_registry",
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finding_class": "exploratory",
        "seed": SEED,
        "result": {"n_models": len(models), "missing_artifacts": missing, "models": models},
    }
    path = REPORTS_DIR / "model_registry.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", path, "n", len(models), "missing", missing)


if __name__ == "__main__":
    main()
