import pandas as pd
import joblib
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix
)

# Project paths
DATA_PATH = Path("src/data/train.csv")
MODEL_PATH = Path("src/models/gold_model.pkl")

# Load historical gold data
df = pd.read_csv(DATA_PATH)

# Calculate next available trading session direction
df["Next_Close"] = df["Close"].shift(-1)
df["Target"] = (df["Next_Close"] > df["Close"]).astype(int)

# Generate technical indicators
from src.features import calculate_features

df = calculate_features(df)

# Remove missing and invalid values
df = df.replace([float("inf"), float("-inf")], float("nan"))
df = df.dropna().copy()

# Remove final row because its next close is unknown
df = df.iloc[:-1].copy()

# Features used by the model
feature_columns = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "SMA_20",
    "SMA_50",
    "EMA_20",
    "RSI",
    "MACD",
    "MACD_SIGNAL",
    "BB_UPPER",
    "BB_LOWER",
    "VOLATILITY",
    "MOMENTUM",
]

X = df[feature_columns]
y = df["Target"]

# Train model
model = RandomForestClassifier(
    n_estimators=200,
    max_depth=8,
    min_samples_leaf=10,
    random_state=42,
    class_weight="balanced",
    n_jobs=-1
)

model.fit(X, y)

# Save model and its feature list
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

joblib.dump(
    {
        "model": model,
        "features": feature_columns
    },
    MODEL_PATH
)

# Training-set diagnostics only (not a measure of future performance)
predictions = model.predict(X)

print("\nModel training completed.")
print("Training records:", len(X))
print("Training accuracy:", round(accuracy_score(y, predictions), 4))
print("Training balanced accuracy:", round(balanced_accuracy_score(y, predictions), 4))
print("\nTraining classification report:")
print(classification_report(y, predictions, zero_division=0))
print("\nTraining confusion matrix:")
print(confusion_matrix(y, predictions))
print("\nModel saved at:", MODEL_PATH)