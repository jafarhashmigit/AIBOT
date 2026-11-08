"""Chronological 70/15/15 split of the labeled XAUUSD M5 dataset.

Rows are never shuffled. The label on row t uses bars t+1 .. t+12, so the last
PURGE_BARS (12) rows before each boundary are removed from the earlier split;
otherwise their labels would be built from prices inside the next split.

Saved files keep `time` as a row identifier only. Model inputs are given by
get_feature_columns(), which excludes `time`, prices, identifiers and `target`.
"""

from pathlib import Path

import pandas as pd

from features_m5 import BAR_MINUTES
from label_m5 import OUTPUT_PATH as LABELED_PATH
from label_m5 import PURGE_BARS, TARGET_COLUMN, TARGET_NAMES

DATA_DIR = Path(__file__).resolve().parent / "data"
SPLIT_PATHS = {
    "train": DATA_DIR / "xauusd_m5_train.csv",
    "validation": DATA_DIR / "xauusd_m5_validation.csv",
    "test": DATA_DIR / "xauusd_m5_test.csv",
}
# Older project files with generic names that must never be overwritten.
PROTECTED_PATHS = {DATA_DIR / name for name in ("train.csv", "validation.csv", "test.csv")}

TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15

LABEL_WINDOW = pd.Timedelta(minutes=BAR_MINUTES * PURGE_BARS)
NON_FEATURE_COLUMNS = {"time", "time_utc", "open", "high", "low", "close", TARGET_COLUMN}


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS]


def load_labeled(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%d %H:%M:%S")
    if not df["time"].is_monotonic_increasing or not df["time"].is_unique:
        raise ValueError("Labeled data must be strictly chronological with unique timestamps.")
    if not df[TARGET_COLUMN].isin(TARGET_NAMES).all():
        raise ValueError(f"Unexpected values in '{TARGET_COLUMN}'.")
    if df.isna().any().any():
        raise ValueError("Labeled data contains missing values.")
    return df


def chronological_split(df: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    n = len(df)
    validation_start = int(n * TRAIN_FRACTION)
    test_start = int(n * (TRAIN_FRACTION + VALIDATION_FRACTION))

    splits = {
        "train": df.iloc[: validation_start - PURGE_BARS],
        "validation": df.iloc[validation_start : test_start - PURGE_BARS],
        "test": df.iloc[test_start:],
    }
    purged = {
        "train -> validation": df.iloc[validation_start - PURGE_BARS : validation_start],
        "validation -> test": df.iloc[test_start - PURGE_BARS : test_start],
    }
    return splits, purged


def validate_splits(splits: dict[str, pd.DataFrame], purged: dict[str, pd.DataFrame], total: int) -> None:
    for name, part in splits.items():
        assert len(part) > 0, f"{name} split is empty"
        assert part["time"].is_monotonic_increasing and part["time"].is_unique, f"{name} not chronological"
        assert not part.isna().any().any(), f"{name} contains missing values"

    order = ["train", "validation", "test"]
    for earlier, later in zip(order, order[1:]):
        a, b = splits[earlier], splits[later]
        assert a["time"].max() < b["time"].min(), f"{earlier} and {later} timestamps overlap"
        # Last label window of the earlier split must end before the later split's first bar.
        assert a["time"].max() + LABEL_WINDOW < b["time"].min(), f"{earlier} labels leak into {later}"

    all_times = pd.concat([p["time"] for p in splits.values()])
    assert all_times.is_unique, "a timestamp appears in more than one split"

    for boundary, rows in purged.items():
        assert len(rows) == PURGE_BARS, f"{boundary}: expected {PURGE_BARS} purged rows, got {len(rows)}"

    kept = sum(len(p) for p in splits.values())
    removed = sum(len(p) for p in purged.values())
    assert kept + removed == total, "rows lost or duplicated during splitting"


def describe(splits: dict[str, pd.DataFrame], purged: dict[str, pd.DataFrame], total: int) -> None:
    print(f"Labeled rows: {total}")
    print(f"Purge per boundary: {PURGE_BARS} rows (label window t+1 .. t+{PURGE_BARS})\n")

    for name, part in splits.items():
        print(f"{name.upper()}")
        print(f"  rows: {len(part)} ({len(part) / total:.2%} of labeled rows)")
        print(f"  date range: {part['time'].iloc[0]} -> {part['time'].iloc[-1]}")
        names = part[TARGET_COLUMN].map(TARGET_NAMES)
        counts = names.value_counts().reindex(["BUY", "SELL", "WAIT"], fill_value=0)
        dist = ", ".join(f"{k} {v} ({v / len(part):.1%})" for k, v in counts.items())
        print(f"  classes: {dist}")
        print(f"  missing values: {int(part.isna().sum().sum())}\n")

    for boundary, rows in purged.items():
        print(f"Purged at {boundary}: {len(rows)} rows, {rows['time'].iloc[0]} -> {rows['time'].iloc[-1]}")

    order = ["train", "validation", "test"]
    for earlier, later in zip(order, order[1:]):
        last_end = splits[earlier]["time"].iloc[-1] + LABEL_WINDOW
        first = splits[later]["time"].iloc[0]
        print(f"{earlier} last label window ends {last_end} < {later} starts {first}")


def main() -> None:
    df = load_labeled(LABELED_PATH)
    feature_columns = get_feature_columns(df)

    splits, purged = chronological_split(df)
    validate_splits(splits, purged, len(df))
    describe(splits, purged, len(df))

    columns = ["time"] + feature_columns + [TARGET_COLUMN]
    print()
    for name, path in SPLIT_PATHS.items():
        if path in PROTECTED_PATHS:
            raise RuntimeError(f"Refusing to overwrite existing project file {path}")
        out = splits[name][columns].copy()
        out["time"] = out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        out.to_csv(path, index=False)
        print(f"Saved {name}: {path}")

    print(f"\nModel features ({len(feature_columns)}): excludes {sorted(NON_FEATURE_COLUMNS & set(df.columns))}")
    print("No missing values in any split: True")


if __name__ == "__main__":
    main()
