"""Random Forest diagnostic baseline for the XAUUSD M5 triple-barrier labels.

Trains on the training split and evaluates on the validation split only. The
test split is never loaded. Hyperparameters are fixed baseline values, not tuned.
This is a diagnostic baseline, not evidence of a profitable strategy.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    precision_score,
)

from label_m5 import SL_ATR_MULTIPLE, TARGET_COLUMN, TARGET_NAMES, TP_ATR_MULTIPLE

SRC_DIR = Path(__file__).resolve().parent
TRAIN_PATH = SRC_DIR / "data" / "xauusd_m5_train.csv"
VALIDATION_PATH = SRC_DIR / "data" / "xauusd_m5_validation.csv"
MODEL_PATH = SRC_DIR / "models" / "rf_m5_baseline.pkl"

RANDOM_STATE = 42

RF_FEATURES = [
    # trend (scale-free)
    "close_to_ema_9", "close_to_ema_50", "ema_9_20_spread", "ema_20_50_spread",
    # oscillators / bands
    "rsi_14", "bb_percent_b", "bb_width",
    # volatility
    "atr_14_pct", "volatility_12", "volatility_48", "volatility_ratio_12_48",
    # candle shape
    "candle_body_abs_to_range", "upper_wick_to_range", "lower_wick_to_range", "candle_range_to_atr",
    # returns / momentum
    "log_return_1", "return_3", "return_6", "return_12", "roc_20",
    # tick volume
    "log_tick_volume", "tick_volume_change", "tick_volume_ratio_20",
    # time / session / gaps
    "hour_utc", "weekday",
    "session_asia", "session_london", "session_new_york", "session_london_ny_overlap",
    "minutes_since_prev_bar",
]

# Shallow-ish trees with large leaves: M5 labels are noisy and consecutive labels
# overlap, so max_samples < 1 also keeps bootstrap samples less redundant.
RF_PARAMS = {
    "n_estimators": 300,
    "max_depth": 8,
    "min_samples_leaf": 50,
    "max_features": "sqrt",
    "max_samples": 0.5,
    "bootstrap": True,
    "class_weight": "balanced",
    "criterion": "gini",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

FORBIDDEN_INPUTS = {"time", "time_utc", "open", "high", "low", "close", TARGET_COLUMN}
CLASS_ORDER = [1, -1, 0]  # BUY, SELL, WAIT
CLASS_LABELS = [TARGET_NAMES[c] for c in CLASS_ORDER]
BREAKEVEN_PRECISION = SL_ATR_MULTIPLE / (TP_ATR_MULTIPLE + SL_ATR_MULTIPLE)


def load_split(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%d %H:%M:%S")
    missing = [c for c in RF_FEATURES + [TARGET_COLUMN] if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")
    if not df["time"].is_monotonic_increasing:
        raise ValueError(f"{path.name} is not in chronological order.")

    X = df[RF_FEATURES]
    y = df[TARGET_COLUMN]
    if not np.isfinite(X.to_numpy(dtype=float)).all():
        raise ValueError(f"{path.name} has missing or infinite feature values.")
    if not y.isin(CLASS_ORDER).all():
        raise ValueError(f"{path.name} has unexpected target values.")
    return df, X, y


def validate_inputs(X_train: pd.DataFrame, X_val: pd.DataFrame, train: pd.DataFrame, val: pd.DataFrame) -> None:
    assert len(RF_FEATURES) == 30 and len(set(RF_FEATURES)) == 30, "RF_FEATURES must be 30 unique columns"
    assert not FORBIDDEN_INPUTS & set(RF_FEATURES), "time/price/target columns in RF_FEATURES"
    assert list(X_train.columns) == RF_FEATURES == list(X_val.columns), "feature order mismatch"
    assert train["time"].max() < val["time"].min(), "validation does not start after training"


def print_dataset_info(name: str, df: pd.DataFrame, X: pd.DataFrame, y: pd.Series) -> None:
    counts = y.map(TARGET_NAMES).value_counts().reindex(CLASS_LABELS, fill_value=0)
    dist = ", ".join(f"{k} {v} ({v / len(y):.1%})" for k, v in counts.items())
    print(f"{name}: X {X.shape}, y {y.shape}, {df['time'].iloc[0]} -> {df['time'].iloc[-1]}")
    print(f"  classes: {dist}")


def evaluate(name: str, model: RandomForestClassifier, X: pd.DataFrame, y: pd.Series) -> None:
    pred = model.predict(X)
    print(f"\n=== {name} ===")
    print(f"Accuracy:          {accuracy_score(y, pred):.4f}")
    print(f"Balanced accuracy: {balanced_accuracy_score(y, pred):.4f}")
    majority = y.value_counts(normalize=True).max()
    print(f"Majority-class accuracy (reference): {majority:.4f}")

    cm = confusion_matrix(y, pred, labels=CLASS_ORDER)
    cm_df = pd.DataFrame(cm, index=[f"true {c}" for c in CLASS_LABELS], columns=[f"pred {c}" for c in CLASS_LABELS])
    print("\nConfusion matrix:")
    print(cm_df.to_string())

    print("\nClassification report:")
    print(classification_report(y, pred, labels=CLASS_ORDER, target_names=CLASS_LABELS, digits=4, zero_division=0))

    precision = precision_score(y, pred, labels=CLASS_ORDER, average=None, zero_division=0)
    pred_counts = pd.Series(pred).map(TARGET_NAMES).value_counts()
    for cls, label, p in zip(CLASS_ORDER, CLASS_LABELS, precision):
        if cls == 0:
            continue
        signals = int(pred_counts.get(label, 0))
        print(f"{label} precision: {p:.4f} over {signals} signals "
              f"(break-even win rate {BREAKEVEN_PRECISION:.2%} for TP {TP_ATR_MULTIPLE} / SL {SL_ATR_MULTIPLE} ATR)")


def print_feature_importance(model: RandomForestClassifier) -> None:
    importance = pd.Series(model.feature_importances_, index=RF_FEATURES).sort_values(ascending=False)
    print("\nFeature importance (impurity-based, from training data):")
    for rank, (feature, value) in enumerate(importance.items(), 1):
        print(f"  {rank:2d}. {feature:<28s} {value:.4f}")


def main() -> None:
    train, X_train, y_train = load_split(TRAIN_PATH)
    val, X_val, y_val = load_split(VALIDATION_PATH)
    validate_inputs(X_train, X_val, train, val)

    print("Datasets (test split is not loaded)")
    print_dataset_info("Train", train, X_train, y_train)
    print_dataset_info("Validation", val, X_val, y_val)
    print(f"Features ({len(RF_FEATURES)}): {RF_FEATURES}")

    model = RandomForestClassifier(**RF_PARAMS)
    model.fit(X_train, y_train)

    print("\nModel parameters:")
    for key, value in sorted(model.get_params().items()):
        print(f"  {key}: {value}")

    evaluate("TRAINING (in-sample, optimistic)", model, X_train, y_train)
    evaluate("VALIDATION (out-of-sample)", model, X_val, y_val)
    print_feature_importance(model)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": RF_FEATURES,
            "target_mapping": TARGET_NAMES,
            "params": RF_PARAMS,
            "train_range": (str(train["time"].iloc[0]), str(train["time"].iloc[-1])),
        },
        MODEL_PATH,
    )
    print(f"\nModel saved: {MODEL_PATH}")
    print("Diagnostic baseline only: accuracy here is not evidence of profitability.")


if __name__ == "__main__":
    main()
