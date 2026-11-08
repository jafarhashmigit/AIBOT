import pandas as pd
import joblib

from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix
)

from src.features import calculate_features

# Load trained model
saved = joblib.load("src/models/gold_model.pkl")
model = saved["model"]
feature_columns = saved["features"]


def evaluate(data_path, dataset_name):
    print(f"\n{'=' * 45}")
    print(f"Evaluating: {dataset_name}")
    print(f"{'=' * 45}")

    # Load data
    df = pd.read_csv(data_path)

    # Create next-session target
    df["Next_Close"] = df["Close"].shift(-1)
    df["Target"] = (df["Next_Close"] > df["Close"]).astype(int)

    # Calculate indicators
    df = calculate_features(df)

    # Clean data
    df = df.replace([float("inf"), float("-inf")], float("nan"))
    df = df.dropna().copy()

    # Remove final row (unknown next close)
    df = df.iloc[:-1].copy()

    X = df[feature_columns]
    y = df["Target"]

    # Predict without retraining
    predictions = model.predict(X)

    print("Records:", len(X))
    print("Accuracy:", round(accuracy_score(y, predictions), 4))
    print(
        "Balanced Accuracy:",
        round(balanced_accuracy_score(y, predictions), 4)
    )

    print("\nClassification Report:")
    print(classification_report(y, predictions, zero_division=0))

    print("Confusion Matrix:")
    print(confusion_matrix(y, predictions))


# Evaluate separately
evaluate("src/data/validation.csv", "VALIDATION DATA")
evaluate("src/data/test.csv", "TEST DATA")